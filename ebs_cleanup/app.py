import datetime
import json
import logging
import os
import re

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError


LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

IGNORE_TAG = "lambda-ebs-cleanup:ignore"


def parse_age(age_string):
    """Input string format: integer suffixed with 's', 'm', or 'd',
    for seconds, minutes, or days respectively.

    Returns a datetime.timedelta object."""

    delta = None

    pat = re.compile(r'(\d+)([smd])')
    mat = pat.search(age_string)

    age = int(mat.group(1))
    unit = mat.group(2)

    if unit == 's':
        delta = datetime.timedelta(seconds=age)
    elif unit == 'm':
        delta = datetime.timedelta(minutes=age)
    elif unit == 'd':
        delta = datetime.timedelta(days=age)

    return delta


def local_volume_filter(volumes, age_string):
    """Client-side filtering of the volume list returned by EC2"""
    output = []

    for v in volumes:
        # double-check for attachments
        if v['Attachments']:
            LOG.error(f"Volume {v['VolumeId']} has attachments: {v['Attachments']}")
            continue

        # check the age is greater than the minimum allowed age to avoid race
        # conditions that could delete a new volume before it is attached
        tz = v['CreateTime'].tzinfo  # Copy the timezone from the creation time
        td = parse_age(age_string)
        if datetime.datetime.now(tz) - v['CreateTime'] < td:
            LOG.info(f"Skipping volume {v['VolumeId']} created at {v['CreateTime']}")
            continue

        # Ignore any volumes marked with the appropirate tag ('lambda-ebs-cleanup:ignore' == 'True')
        LOG.info(f"Tags: {v['Tags']}")
        skip_tag = False
        if v['Tags']:  # skip the case where tags is None (not iterable)
            for tag in v['Tags']:
                if 'Key' in tag and tag['Key'] == IGNORE_TAG:
                    if 'Value' in tag and tag['Value'] in ['True', 'true']:
                        LOG.info(f"Skipping {v['VolumeId']} due to {IGNORE_TAG} tag")
                        skip_tag = True
                if 'key' in tag and tag['key'] == IGNORE_TAG:
                    if 'value' in tag and tag['value'] in ['True', 'true']:
                        LOG.info(f"Skipping {v['VolumeId']} due to {IGNORE_TAG} tag")
                        skip_tag = True
        if skip_tag:
            continue

        LOG.info(f"Marking unattached volume {v['VolumeId']} for deletion")
        output.append(v)
    return output


def get_regions(client):
    return [r['RegionName'] for r in client.describe_regions()['Regions']]


def scan_region(client, min_age):
    """Check each region for unattached (available) or errored EBS volumes"""

    results = []
    vfilter = {
        'Name': 'status',
        'Values': ['available', 'error']
    }

    volumes = client.describe_volumes(Filters=[vfilter], MaxResults=100)

    token = ''
    if 'NextToken' in volumes:
        token = volumes['NextToken']
        LOG.info(f"Found next token: {token}")

    results.extend(volumes['Volumes'])

    while token != '':
        volumes = client.describe_volumes(
                Filters=[vfilter],
                MaxResults=100,
                NextToken=token)

        if 'NextToken' in volumes:
            token = volumes['NextToken']
            LOG.info(f"Found next token: {token}")
            results.extend(volumes['Volumes'])
        else:
            LOG.warning('No NextToken found')
            token = ''

    return local_volume_filter(results, min_age)


def lambda_handler(event, context):
    """Sample pure Lambda function

    Parameters
    ----------
    event: dict, required
        API Gateway Lambda Proxy Input Format

        Event doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format

    context: object, required
        Lambda Context runtime methods and attributes

        Context doc: https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    Returns
    ------
    API Gateway Lambda Proxy Output Format: dict

        Return doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
    """

    try:
        unattached = []
        min_age = os.environ.get('ebsMinimumAge', '5m')
        client = boto3.client('ec2')
        regions = get_regions(client)

        for r in regions:
            rconfig = BotoConfig(region_name=r)
            rclient = boto3.client('ec2', config=rconfig)
            unattached.extend(scan_region(rclient, min_age))

        vcount = len(unattached)
        LOG.info(f"Found {vcount} unattached/errored EBS volumes")

        deleted = []
        for v in unattached:
            # delete the volume
            vol_id = v['VolumeId']
            LOG.info(f"Deleting unattached/errored volume {vol_id}")
            deleted.append(vol_id)
            client.delete_volume(VolumeId=vol_id)

        message = f"Unattached/errored volumes deleted: {deleted}"
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": message,
            }),
        }

    except ClientError as e:
        LOG.exception(e)
        message = e.response['Error']['Message']
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": message,
            }),
        }

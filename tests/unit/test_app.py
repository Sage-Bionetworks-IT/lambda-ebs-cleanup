from ebs_cleanup import app

import datetime
import json
import os
import random

import boto3
import botocore
import pytest
from botocore.stub import Stubber


def volume_factory(volume_id, create_time, attachments, tags):
    result = {}
    result['VolumeId'] = str(volume_id)  # coerce ints to strings
    result['CreateTime'] = create_time
    result['Attachments'] = attachments
    if tags is not None:
        result['Tags'] = tags
    return result

def test_local_filter():
    """
    Create mock volumes and run them through the local volume filter.
    The first mock volume should pass through the filter, the second
    should be filtered out based on attachments. The third should be
    filtered out based on creation time. The fourth should be filtered
    out based on tags."""

    now = datetime.datetime.now()
    yesterday = now - datetime.timedelta(days=1)

    mv1 = volume_factory(1, yesterday, [], None)
    mv2 = volume_factory(2, yesterday, ["mystery-volume",], [])
    mv3 = volume_factory(3, now, [], [])
    mv4 = volume_factory(4, yesterday, [], [{'Key': 'lambda-ebs-cleanup:ignore', 'Value': 'True'}])
    mock_volume_list = [mv1, mv2, mv3, mv4]

    # Run the mock volumes through the local volume filter,
    # which should filter out mv2 based on attachments
    # and mv3 based on creation time
    ret = app.local_volume_filter(mock_volume_list, '5m')
    assert mv1 in ret
    assert mv2 not in ret
    assert mv3 not in ret
    assert mv4 not in ret

def test_parse_age():
    random.seed()
    age = random.randint(1, 20)

    day_str = f"{age}d"
    day_date = datetime.timedelta(days=age)

    min_str = f"{age}m"
    min_date = datetime.timedelta(minutes=age)

    sec_str = f"{age}s"
    sec_date = datetime.timedelta(seconds=age)

    day_out = app.parse_age(day_str)
    min_out = app.parse_age(min_str)
    sec_out = app.parse_age(sec_str)

    assert day_out == day_date
    assert min_out == min_date
    assert sec_out == sec_date

def test_scan(mocker):
    now = datetime.datetime.now()
    yesterday = now - datetime.timedelta(days=1)

    mv1 = volume_factory(1, yesterday, [], [])
    mv2 = volume_factory(2, yesterday, [], None)
    mv3 = volume_factory(3, yesterday, [], [])
    mv4 = volume_factory(4, now, [], [])

    # simulate a long list of volumes
    resp1 = {'Volumes': [mv1, mv2], 'NextToken': 'arbitrary'}
    resp2 = {'Volumes': [mv3, mv4], 'NextToken': ''}

    expected = [mv1, mv2, mv3]

    min_age = '30m'

    mocker.patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'test-region'})
    ec2 = boto3.client('ec2')

    with Stubber(ec2) as stub:
        stub.add_response('describe_volumes', resp1)
        stub.add_response('describe_volumes', resp2)

        found = app.scan_region(ec2, min_age)

    assert found == expected

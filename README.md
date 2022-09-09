# lambda-ebs-cleanup
An AWS lambda to scan all regions for unattached EBS volumes and delete them.

This lambda will scan all regions active for the current account, looking
for EBS volumes older than a specified age (default five minutes) that have
a status of either `error` or `available` (aka 'unattached'). Any volumes
with a `lambda-ebs-cleanup:ignore` tag set to `True` will be ignored.
Once all matching volumes are found, deletes are issued for each.

## Development

### Contributions
Contributions are welcome.

### Requirements
Run `pipenv install --dev` to install both production and development
requirements, and `pipenv shell` to activate the virtual environment. For more
information see the [pipenv docs](https://pipenv.pypa.io/en/latest/).

After activating the virtual environment, run `pre-commit install` to install
the [pre-commit](https://pre-commit.com/) git hook.

### Create a local build

```shell script
$ sam build
```

### Run unit tests
Tests are defined in the `tests` folder in this project. Use PIP to install the
[pytest](https://docs.pytest.org/en/latest/) and run unit tests.

```shell script
$ python -m pytest tests/ -v
```

### Run integration tests
Running integration tests
[requires docker](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference-sam-local-start-api.html)

```shell script
$ sam local invoke EbsCleanupFunction --event events/event.json
```

## Deployment

### Deploy Lambda to S3
Deployments are sent to the
[Sage cloudformation repository](https://bootstrap-awss3cloudformationbucket-19qromfd235z9.s3.amazonaws.com/index.html)
which requires permissions to upload to Sage
`bootstrap-awss3cloudformationbucket-19qromfd235z9` and
`essentials-awss3lambdaartifactsbucket-x29ftznj6pqw` buckets.

```shell script
sam package --template-file .aws-sam/build/template.yaml \
  --s3-bucket essentials-awss3lambdaartifactsbucket-x29ftznj6pqw \
  --output-template-file .aws-sam/build/lambda-ebs-cleanup.yaml

aws s3 cp .aws-sam/build/lambda-ebs-cleanup.yaml s3://bootstrap-awss3cloudformationbucket-19qromfd235z9/lambda-ebs-cleanup/master/
```

## Publish Lambda

### Private access
Publishing the lambda makes it available in your AWS account.  It will be accessible in
the [serverless application repository](https://console.aws.amazon.com/serverlessrepo).

```shell script
sam publish --template .aws-sam/build/lambda-ebs-cleanup.yaml
```

### Public access
Making the lambda publicly accessible makes it available in the
[global AWS serverless application repository](https://serverlessrepo.aws.amazon.com/applications)

```shell script
aws serverlessrepo put-application-policy \
  --application-id <lambda ARN> \
  --statements Principals=*,Actions=Deploy
```

## Install Lambda into AWS

### Sceptre
Create the following [sceptre](https://github.com/Sceptre/sceptre) file
config/prod/lambda-ebs-cleanup.yaml

```yaml
template:
  type: http
  url: "https://bootstrap-awss3cloudformationbucket-19qromfd235z9.s3.amazonaws.com/lambda-ebs-cleanup/master/lambda-ebs-cleanup.yaml"
stack_name: "lambda-ebs-cleanup"
stack_tags:
  Department: "Platform"
  Project: "Infrastructure"
  OwnerEmail: "it@sagebase.org"
```

Install the lambda using sceptre:
```shell script
sceptre --var "profile=my-profile" --var "region=us-east-1" launch prod/lambda-ebs-cleanup.yaml
```

### AWS Console
Steps to deploy from AWS console.

1. Login to AWS
2. Access the
[serverless application repository](https://console.aws.amazon.com/serverlessrepo)
-> Available Applications
3. Select application to install
4. Enter Application settings
5. Click Deploy

## Releasing

We have setup our CI to automate a releases.  To kick off the process just create
a tag (i.e 0.0.1) and push to the repo.  The tag must be the same number as the current
version in [template.yaml](template.yaml).  Our CI will do the work of deploying and publishing
the lambda.

## Running

### Scheduled Runs
By default the lambda is scheduled to run daily at 2AM. This can be configured with the
`Schedule` paramater using [this schedule format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/events/ScheduledEvents.html).

### Triggering Manually

Once a released template is deployed as a cloudformation stack, locate the `EbsCleanupApi`
output of the stack and make a simple GET request to the URL; for example:

```shell
curl https://RANDOM_STRING.execute-api.us-east-1.amazonaws.com/Prod/clean
```

# CloudFormation Deployment

This directory contains CloudFormation templates to deploy the Bedrock Agent Chat Completions Proxy to AWS.

## Quick Deployment

### Step 1: Configure AWS Credentials

Ensure your AWS credentials are configured. You can do this in several ways:

1. Environment variables:
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_REGION=us-east-1  # or your preferred region
```

2. AWS CLI configuration:
```bash
aws configure
```

3. IAM role (if deploying from an EC2 instance or other AWS service)

### Step 2: Pre-deployment Checklist

1. Ensure you have:
   - [ ] AWS credentials with necessary permissions
   - [ ] Selected target AWS region with Bedrock Agent support
   - [ ] For Fargate: Docker image built and pushed to ECR

2. Required IAM Permissions:
   - `bedrock:InvokeAgent`
   - `cloudformation:CreateStack`
   - For Fargate: `ecr:*` permissions

### Step 3: Deploy the CloudFormation Stack

1. Sign in to AWS Management Console and switch to your desired region
2. Click one of the following buttons to launch the CloudFormation Stack:

   - **Lambda Deployment** (recommended for variable workloads)

     [![Launch Stack](assets/launch-stack.png)](https://console.aws.amazon.com/cloudformation/home#/stacks/create/template?stackName=BedrockAgentProxy&templateURL=https://raw.githubusercontent.com/DamienDeepgram/amazon-bedrock-agent-chat-completions-proxy/main/cloud_formation_template/BedrockAgentProxyLambda.yaml)

   - **Fargate Deployment** (recommended for consistent workloads)

     [![Launch Stack](assets/launch-stack.png)](https://console.aws.amazon.com/cloudformation/home#/stacks/create/template?stackName=BedrockAgentProxy&templateURL=https://raw.githubusercontent.com/DamienDeepgram/amazon-bedrock-agent-chat-completions-proxy/main/cloud_formation_template/BedrockAgentProxyFargate.yaml)

3. Click "Next"
4. On the "Specify stack details" page:
   - Stack name: Change if needed (default: BedrockAgentProxy)
   - Stage: Deployment stage (default: prod)
   - For Lambda deployment:
     - ProvisionedConcurrency: Number of warm Lambda instances (default: 5)
   - For both:
     - CreateVpc: Whether to create a new VPC (default: true)
     - VpcId: Existing VPC ID (if CreateVpc is false)
     - SubnetIds: Existing subnet IDs (if CreateVpc is false)

5. Click "Next"
6. On "Configure stack options", adjust as needed or keep defaults
7. Click "Next"
8. Review the configuration and check "I acknowledge that AWS CloudFormation might create IAM resources"
9. Click "Create stack"

That's it! 🎉 Once deployed:
1. Go to the CloudFormation stack's "Outputs" tab
2. Find the `ApiEndpoint` value - this is your API endpoint
3. For Lambda deployments, you'll also see `DirectLambdaUrl` for lower latency access

## Manual Deployment

## Available Templates

1. **Lambda Deployment** (`BedrockAgentProxyLambda.yaml`):
   - Serverless deployment using AWS Lambda
   - API Gateway integration
   - Supports streaming responses
   - Best for variable workloads and cost optimization

2. **Fargate Deployment** (`BedrockAgentProxyFargate.yaml`):
   - Container-based deployment using ECS Fargate
   - Application Load Balancer integration
   - Better for consistent high throughput
   - Avoids cold starts entirely

## Choosing a Deployment Option

### Lambda Deployment (`BedrockAgentProxyLambda.yaml`)

Choose this if you:
- Have variable or unpredictable workloads
- Want lower costs for inconsistent usage
- Need quick auto-scaling
- Want simpler deployment and updates

Features:
- Provisioned concurrency for reduced cold starts
- API Gateway with caching
- Multiple access methods (ALB, API Gateway, Function URL)
- Comprehensive monitoring with X-Ray and CloudWatch

### Fargate Deployment (`BedrockAgentProxyFargate.yaml`)

Choose this if you:
- Have steady, high-throughput workloads
- Need consistent performance
- Want to avoid cold starts entirely
- Need longer processing times
- Prefer container-based deployment

Features:
- ECS Fargate for reliable container execution
- Application Load Balancer for high availability
- Container-level metrics and monitoring
- Better for long-running processes

## Prerequisites

1. AWS CLI installed and configured
2. The proxy code from the parent directory
3. For Fargate: Docker installed and access to Amazon ECR

## Deployment Steps

### Lambda Deployment

1. Package the Lambda function:
```bash
cd ..
zip -r cloud_formation_template/function.zip app.py
cd cloud_formation_template
```

2. Deploy the stack:
```bash
aws cloudformation create-stack \
  --stack-name bedrock-agent-proxy \
  --template-body file://BedrockAgentProxyLambda.yaml \
  --parameters \
    ParameterKey=Stage,ParameterValue=prod \
    ParameterKey=ProvisionedConcurrency,ParameterValue=5 \
  --capabilities CAPABILITY_IAM
```

### Fargate Deployment

1. Create ECR repository (if not exists):
```bash
aws ecr create-repository --repository-name bedrock-agent-proxy
```

2. Build and push the Docker image:
```bash
aws ecr get-login-password --region REGION | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.REGION.amazonaws.com
docker build -t bedrock-agent-proxy .
docker tag bedrock-agent-proxy:latest ACCOUNT.dkr.ecr.REGION.amazonaws.com/bedrock-agent-proxy:latest
docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/bedrock-agent-proxy:latest
```

3. Deploy the stack:
```bash
aws cloudformation create-stack \
  --stack-name bedrock-agent-proxy \
  --template-body file://BedrockAgentProxyFargate.yaml \
  --parameters \
    ParameterKey=ApiKeyParam,ParameterValue="" \
  --capabilities CAPABILITY_IAM
```

## Usage

Both deployments support the same API interface. The Agent ID and Alias ID are passed through headers:

```bash
curl -X POST https://YOUR_ENDPOINT/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Agent-Id: YOUR_AGENT_ID" \
  -H "X-Agent-Alias-Id: YOUR_AGENT_ALIAS_ID" \
  -H "X-Agent-Region: us-east-1" \
  -H "X-Session-Id: your-unique-session-id" \
  -d '{
    "model": "bedrock-agent",
    "messages": [
      {"role": "user", "content": "Hello?"}
    ],
    "stream": true
  }'
```

### Headers

| Header | Required | Description |
|--------|----------|-------------|
| X-Agent-Id | Yes | Your Bedrock Agent ID |
| X-Agent-Alias-Id | Yes | Your Bedrock Agent Alias ID |
| X-Agent-Region | No | Region where your agent is deployed (defaults to stack region) |
| X-Session-Id | No | Session ID for conversation context |

### Endpoints

Lambda deployment provides three endpoints:
1. Load Balancer endpoint (recommended)
2. API Gateway endpoint
3. Direct Lambda URL (lowest latency)

Fargate deployment provides:
1. Load Balancer endpoint

## Monitoring

### Lambda Deployment
- Lambda execution metrics
- API Gateway metrics
- X-Ray traces
- CloudWatch Logs

### Fargate Deployment
- Container metrics
- ECS service metrics
- Load balancer metrics
- CloudWatch Logs

## Security

Both templates include:
- VPC isolation
- Security groups
- IAM roles with minimal permissions
- Load balancer security

Additional considerations:
- Add authentication for production use
- Enable SSL/TLS termination
- Implement API key validation
- Configure network ACLs

## Cleanup

To remove the deployed resources:

```bash
aws cloudformation delete-stack --stack-name bedrock-agent-proxy
```

For Fargate deployment, also clean up the ECR repository if needed:
```bash
aws ecr delete-repository --repository-name bedrock-agent-proxy --force
```

## Environment Variables

The following environment variables are supported:

### Optional Variables
- `DEBUG`: Enable debug logging (true/false)
- `SESSION_TTL`: Session timeout in seconds (default: 3600)

### Lambda-specific Variables
- `POWERTOOLS_SERVICE_NAME`: Service name for AWS Lambda Powertools
- `POWERTOOLS_METRICS_NAMESPACE`: Metrics namespace for CloudWatch

### Fargate-specific Variables
- `AWS_LOG_GROUP`: CloudWatch Log Group name
- `AWS_LOG_STREAM`: CloudWatch Log Stream prefix

## Security Best Practices

1. **Parameter Store**:
   - Use SecureString for sensitive values
   - Implement parameter rotation
   - Use AWS KMS for encryption

2. **Network Security**:
   - Consider using private subnets with NAT Gateway
   - Restrict security group ingress rules
   - Enable VPC Flow Logs

3. **API Security**:
   - Implement API key validation
   - Consider adding AWS WAF
   - Enable CloudWatch logging 
## MCP Route Testing

1. Test the Gateway/route
```
export GATEWAY_IP=$(kubectl get svc agentgateway -n gloo-system -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo $GATEWAY_IP
```

2. Open MCP Inspector
```
npx modelcontextprotocol/inspector#0.16.2
```

URL to put into Inspector: `http://YOUR_ALB_LB_IP:8080/mcp`

## Secure Connectivity To An MCP Server (StreamableHTTP)

1. Add in a traffic policy for auth based on a JWT token
```
kubectl apply -f- <<EOF
apiVersion: gloo.solo.io/v1alpha1
kind: GlooTrafficPolicy
metadata:
  name: jwt
  namespace: gloo-system
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: agentgateway
  glooJWT:
    beforeExtAuth:
      providers:
        selfminted:
          issuer: solo.io
          jwks:
            local:
              key: '{"keys":[{"kty":"RSA","kid":"solo-public-key-001","use":"sig","alg":"RS256","n":"AOfIaJMUm7564sWWNHaXt_hS8H0O1Ew59-nRqruMQosfQqa7tWne5lL3m9sMAkfa3Twx0LMN_7QqRDoztvV3Wa_JwbMzb9afWE-IfKIuDqkvog6s-xGIFNhtDGBTuL8YAQYtwCF7l49SMv-GqyLe-nO9yJW-6wIGoOqImZrCxjxXFzF6mTMOBpIODFj0LUZ54QQuDcD1Nue2LMLsUvGa7V1ZHsYuGvUqzvXFBXMmMS2OzGir9ckpUhrUeHDCGFpEM4IQnu-9U8TbAJxKE5Zp8Nikefr2ISIG2Hk1K2rBAc_HwoPeWAcAWUAR5tWHAxx-UXClSZQ9TMFK850gQGenUp8","e":"AQAB"}]}'
EOF
```

2. Save the token for "Bob"
```
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InNvbG8tcHVibGljLWtleS0wMDEifQ.eyJpc3MiOiJzb2xvLmlvIiwib3JnIjoic29sby5pbyIsInN1YiI6ImJvYiIsInRlYW0iOiJvcHMiLCJleHAiOjIwNzQyNzQ5NTQsImxsbXMiOnsibWlzdHJhbGFpIjpbIm1pc3RyYWwtbGFyZ2UtbGF0ZXN0Il19fQ.GF_uyLpZSTT1DIvJeO_eish1WDjMaS4BQSifGQhqPRLjzu3nXtPkaBRjceAmJi9gKZYAzkT25MIrT42ZIe3bHilrd1yqittTPWrrM4sWDDeldnGsfU07DWJHyboNapYR-KZGImSmOYshJlzm1tT_Bjt3-RK3OBzYi90_wl0dyAl9D7wwDCzOD4MRGFpoMrws_OgVrcZQKcadvIsH8figPwN4mK1U_1mxuL08RWTu92xBcezEO4CdBaFTUbkYN66Y2vKSTyPCxg3fLtg1mvlzU1-Wgm2xZIiPiarQHt6Uq7v9ftgzwdUBQM1AYLvUVhCN6XkkR9OU3p0OXiqEDjAxcg
```

3. Try to re-connect to the MCP Server. You'll see something similar to the below:
```
Connection Error - Check if your MCP server is running and proxy token is correct
```

4. Click on **Authentication**
- Header Name: **Authorization**
- Bearer Token: Bobs Token from step 2

## Specify MCP Server Tool List

You can specify what tools from an MCP Server you want exposed via your AI Gateway

1. Create a policy that specifies no tools listed
```
kubectl apply -f- <<EOF
apiVersion: gateway.kgateway.dev/v1alpha1
kind: TrafficPolicy
metadata:
  name: jwt-rbac
  namespace: gloo-system
spec:
  targetRefs:
    - group: gateway.kgateway.dev
      kind: Backend
      name: mcp-backend
  rbac:
    policy:
      matchExpressions:
        - 'mcp.tool.name == ""'
EOF
```

2. Disconnect and reconnect via the MCP Inspector and you should see no tools

3. Update the policy to include the **Fetch** tool

```
kubectl apply -f- <<EOF
apiVersion: gateway.kgateway.dev/v1alpha1
kind: TrafficPolicy
metadata:
  name: jwt-rbac
  namespace: gloo-system
spec:
  targetRefs:
    - group: gateway.kgateway.dev
      kind: Backend
      name: mcp-backend
  rbac:
    policy:
      matchExpressions:
        - 'mcp.tool.name == "fetch"'
EOF
```

## Connecting To Remote MCP Servers

1. Create the github pat token environment variable:
```
export GITHUB_PERSONAL_ACCESS_TOKEN=your_github_pat_here
```

2. Create the k8s secret to store the PAT token:
```
kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: github-pat
  namespace: kagent
type: Opaque
stringData:
  GITHUB_PERSONAL_ACCESS_TOKEN: $GITHUB_PERSONAL_ACCESS_TOKEN
EOF
```

3. Create a new MCP Server object in Kubernetes:
```
kubectl apply -f - <<EOF
apiVersion: kagent.dev/v1alpha2
kind: RemoteMCPServer
metadata:
  name: github-mcp-remote
  namespace: kagent
spec:
  description: GitHub Copilot MCP Server
  url: https://api.githubcopilot.com/mcp/
  protocol: STREAMABLE_HTTP
  headersFrom:
    - name: Authorization
      valueFrom:
        type: Secret
        name: github-pat
        key: GITHUB_PERSONAL_ACCESS_TOKEN
  timeout: 5s
  terminateOnClose: true
EOF
```

4. Create a new Agent and use the MCP Server you created in the previous step:
```
kubectl apply -f - <<EOF
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: github-mcp-agent
  namespace: kagent
spec:
  description: This agent can interact with GitHub repositories, issues, pull requests, and more
  type: Declarative
  declarative:
    modelConfig: default-model-config
    systemMessage: |-
      You're a friendly and helpful agent that uses GitHub tools to help with repository management, issues, pull requests, and code review

      # Instructions

      - If user question is unclear, ask for clarification before running any tools
      - Always be helpful and friendly
      - If you don't know how to answer the question DO NOT make things up
        respond with "Sorry, I don't know how to answer that" and ask the user to further clarify the question

      # Response format
      - ALWAYS format your response as Markdown
      - Your response will include a summary of actions you took and an explanation of the result
    tools:
    - type: McpServer
      mcpServer:
        name: github-mcp-remote
        kind: RemoteMCPServer
        toolNames:
        - get_latest_release
        - get_commit
        - get_tag
        - list_branches
EOF
```

4. Look at the Agent configuration and wait until both `READY` and `ACCEPTED` are in a `True` status:
```
kubectl get agents -n kagent
```

5. Open the kagent UI, go to the UI, and ask: `What branches are available under `https://github.com/AdminTurnedDevOps/agentic-demo-repo``

6. Feel free to dive into how it looks "underneath the hood":
```
kubectl describe agent github-mcp-agent -n kagent
```

## Route Agent Traffic Through Agentgateway

prereq: Ensure you have an Anthropic Secret in the `gloo-system` namespace
```
kubectl apply -f- <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: anthropic-secret
  namespace: gloo-system
  labels:
    app: agentgateway
type: Opaque
stringData:
  Authorization: $ANTHROPIC_API_KEY
EOF
```

1. Create the Gateway
```
kubectl apply -f- <<EOF
kind: Gateway
apiVersion: gateway.networking.k8s.io/v1
metadata:
  name: agentgateway-route
  namespace: gloo-system
  labels:
    app: agentgateway-route
spec:
  gatewayClassName: agentgateway-enterprise
  listeners:
  - protocol: HTTP
    port: 8080
    name: http
    allowedRoutes:
      namespaces:
        from: All
EOF
```

2. Retrieve ALB public IP
```
export INGRESS_GW_ADDRESS=$(kubectl get svc -n gloo-system agentgateway-route -o jsonpath="{.status.loadBalancer.ingress[0]['hostname','ip']}")
echo $INGRESS_GW_ADDRESS
```

3. Create the Backend object so agentgateway knows what to route to

```
kubectl apply -f- <<EOF
apiVersion: gateway.kgateway.dev/v1alpha1
kind: Backend
metadata:
  labels:
    app: agentgateway-route
  name: anthropic-routing-backend
  namespace: gloo-system
spec:
  type: AI
  ai:
    llm:
        anthropic:
          authToken:
            kind: SecretRef
            secretRef:
              name: anthropic-secret
          model: "claude-3-5-haiku-latest"
EOF
```

4. Create the route

```
kubectl apply -f- <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: claude
  namespace: gloo-system
  labels:
    app: agentgateway-route
spec:
  parentRefs:
    - name: agentgateway-route
      namespace: gloo-system
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /anthropic
    filters:
    - type: URLRewrite
      urlRewrite:
        path:
          type: ReplaceFullPath
          replaceFullPath: /v1/chat/completions
    backendRefs:
    - name: anthropic-routing-backend
      namespace: gloo-system
      group: gateway.kgateway.dev
      kind: Backend
EOF
```

5. Create Model Config that will be used by the new agent.

```
kubectl apply -f - <<EOF
apiVersion: kagent.dev/v1alpha2
kind: ModelConfig
metadata:
  name: anthropic-model-config
  namespace: kagent
spec:
  apiKeySecret: anthropic-secret
  apiKeySecretKey: Authorization
  model: claude-3-5-haiku-latest
  provider: OpenAI
  openAI:
    baseUrl: YOUR_GATEWAY_IP_FROM_STEP_2:8080/anthropic
EOF
```

6. Create the agent
```
kubectl apply -f - <<EOF
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: testing-agentgateway
  namespace: kagent
spec:
  description: This agent can use a single tool to expand it's Kubernetes knowledge for troubleshooting and deployment
  type: Declarative
  declarative:
    modelConfig: anthropic-model-config
    systemMessage: |-
      You're a friendly and helpful agent that uses the Kubernetes tool to help troubleshooting and deploy environments
  
      # Instructions
  
      - If user question is unclear, ask for clarification before running any tools
      - Always be helpful and friendly
      - If you don't know how to answer the question DO NOT make things up
        respond with "Sorry, I don't know how to answer that" and ask the user to further clarify the question
  
      # Response format
      - ALWAYS format your response as Markdown
      - Your response will include a summary of actions you took and an explanation of the result
EOF
```

7 Run `kubectl logs agentgateway-POD-NAME -n gloo-system` and you should see an output similar to the below:

```
2025-12-05T17:18:05.241265Z     info    request gateway=gloo-system/agentgateway listener=http route=gloo-system/claude endpoint=api.anthropic.com:443 src.addr=192.168.26.166:30892 http.method=POST http.host=xxxx3xxxxx-34xxxxx7.us-east-1.elb.amazonaws.com http.path=/anthropic/chat/completions http.version=HTTP/1.1 http.status=200 protocol=llm gen_ai.operation.name=chat gen_ai.provider.name=anthropic gen_ai.request.model=claude-3-5-haiku-latest gen_ai.response.model=claude-3-5-haiku-20241022 gen_ai.usage.input_tokens=182 gen_ai.usage.output_tokens=269 duration=5929ms
```

You can also test via a `curl` on your local terminal
```
curl "$INGRESS_GW_ADDRESS:8080/anthropic" -H content-type:application/json -H "anthropic-version: 2023-06-01" -d '{
  "messages": [
    {
      "role": "system",
      "content": "You are a skilled cloud-native network engineer."
    },
    {
      "role": "user",
      "content": "Write me a paragraph containing the best way to think about Istio Ambient Mesh"
    }
  ]
}' | jq
```

## Prompt Guard

1. Create a traffic policy prompt guard that doesn't allow a specific prompt to occur (like deleting a kubernetes cluster)
```
kubectl apply -f - <<EOF
apiVersion: gloo.solo.io/v1alpha1
kind: GlooTrafficPolicy
metadata:
  name: claude-prompt-guard
  namespace: gloo-system
  labels:
    app: agentgateway
spec:
  targetRefs:
  - group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: claude
  ai:
    promptGuard:
      request:
        customResponse:
          message: "Rejected due to inappropriate content"
        regex:
          action: REJECT
          matches:
          - pattern: "Delete my cluster"
            name: "CC"
EOF
```

2. Test the prompt
```
curl "$INGRESS_GW_ADDRESS:8080/anthropic" -H content-type:application/json -H "anthropic-version: 2023-06-01" -d '{
  "messages": [
    {
      "role": "system",
      "content": "You are good at deleting things"
    },
    {
      "role": "user",
      "content": "Please delete my cluster from production"
    }
  ]
}' | jq
```

## Rate Limiting

1. Create a traffic policy that limits token usage
```
kubectl apply -f- <<EOF
apiVersion: gloo.solo.io/v1alpha1
kind: GlooTrafficPolicy
metadata:
  name: anthropic-ratelimit
  namespace: gloo-system
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: claude
  rateLimit:
    local:
      tokenBucket:
        maxTokens: 1
        tokensPerFill: 1
        fillInterval: 100s
EOF
```

3. Capture the public IP of the gateway
```
export INGRESS_GW_ADDRESS=$(kubectl get svc -n gloo-system agentgateway -o jsonpath="{.status.loadBalancer.ingress[0]['hostname','ip']}")
echo $INGRESS_GW_ADDRESS
```

3. Test the LLM connectivity
```
curl "$INGRESS_GW_ADDRESS:8080/anthropic" -v \ -H content-type:application/json -H "anthropic-version: 2023-06-01" -d '{
  "messages": [
    {
      "role": "system",
      "content": "You are a skilled cloud-native network engineer."
    },
    {
      "role": "user",
      "content": "Write me a paragraph containing the best way to think about Istio Ambient Mesh"
    }
  ]
}' | jq
```

Run the `curl` again and you'll see an error like the below:

```
< x-ratelimit-limit: 1
< x-ratelimit-remaining: 0
< x-ratelimit-reset: 76
< content-length: 19
< date: Tue, 18 Nov 2025 15:35:45 GMT
```

## Agentic Observability

1. Deploy a Pod Monitor

The `PodMonitor` selector matches `gateway.networking.k8s.io/gateway-class-name: agentgateway`, which will match any Gateway that uses the agentgateway GatewayClass
```
kubectl apply -f - <<EOF
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: agentgateway
  namespace: monitoring
  labels:
    app: agentgateway
    release: kube-prometheus
spec:
  selector:
    matchLabels:
      gateway.networking.k8s.io/gateway-class-name: agentgateway-enterprise
  podMetricsEndpoints:
  - port: metrics
    path: /metrics
    interval: 30s
    scrapeTimeout: 10s
EOF
```

2. Check the dashboard for metrics

```
kubectl --namespace monitoring port-forward svc/kube-prometheus-grafana 3000:80
```

To log into the Grafana UI:

1. Username: admin
2. Password: `kubectl get secret kube-prometheus-grafana -n monitoring -o jsonpath='{.data.admin-password}' | base64 --decode`
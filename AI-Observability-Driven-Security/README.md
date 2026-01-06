# EC Council: AI Observability and Security

## Installation and Configuration

The below should be configured on the cluster prior to getting into the hands-on showing

### kagent

```
helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
    --namespace kagent \
    --create-namespace
```

```
export ANTHROPIC_API_KEY=
```

```
helm upgrade --install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
    --namespace kagent \
    --set providers.default=anthropic \
    --set providers.anthropic.apiKey=$ANTHROPIC_API_KEY \
    --set ui.service.type=LoadBalancer
```


```
kubectl get svc -n kagent
```

### agentgateway

```
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.0/standard-install.yaml
```

```
helm upgrade -i --create-namespace \
  --namespace agentgateway-system \
  --version v2.2.0-main agentgateway-crds oci://ghcr.io/kgateway-dev/charts/agentgateway-crds 
```

```
helm upgrade -i -n agentgateway-system agentgateway oci://ghcr.io/kgateway-dev/charts/agentgateway \
--version v2.2.0-main
```

```
kubectl get pods -n agentgateway-system
```

### MCP Server Deployment

```
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-math-script
  namespace: default
data:
  server.py: |
    import uvicorn
    from mcp.server.fastmcp import FastMCP
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    mcp = FastMCP("Math-Service")

    @mcp.tool()
    def add(a: int, b: int) -> int:
        return a + b

    @mcp.tool()
    def multiply(a: int, b: int) -> int:
        return a * b

    async def handle_mcp(request: Request):
        try:
            data = await request.json()
            method = data.get("method")
            msg_id = data.get("id")
            result = None
            
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "Math-Service", "version": "1.0"}
                }
            
            elif method == "notifications/initialized":
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": True})

            elif method == "tools/list":
                tools_list = await mcp.list_tools()
                result = {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.inputSchema
                        } for t in tools_list
                    ]
                }

            elif method == "tools/call":
                params = data.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {})
                
                # Call the tool
                tool_result = await mcp.call_tool(name, args)
                
                # --- FIX: Serialize the content objects manually ---
                serialized_content = []
                for content in tool_result:
                    if hasattr(content, "type") and content.type == "text":
                        serialized_content.append({"type": "text", "text": content.text})
                    elif hasattr(content, "type") and content.type == "image":
                         serialized_content.append({
                             "type": "image", 
                             "data": content.data, 
                             "mimeType": content.mimeType
                         })
                    else:
                        # Fallback for dictionaries or other types
                        serialized_content.append(content if isinstance(content, dict) else str(content))

                result = {
                    "content": serialized_content,
                    "isError": False
                }

            elif method == "ping":
                result = {}

            else:
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}},
                    status_code=404
                )

            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": result})

        except Exception as e:
            # Print error to logs for debugging
            import traceback
            traceback.print_exc()
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}},
                status_code=500
            )

    app = Starlette(routes=[
        Route("/mcp", handle_mcp, methods=["POST"]),
        Route("/", lambda r: JSONResponse({"status": "ok"}), methods=["GET"])
    ])

    if __name__ == "__main__":
        print("Starting Fixed Math Server on port 8000...")
        uvicorn.run(app, host="0.0.0.0", port=8000)
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-math-server
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-math-server
  template:
    metadata:
      labels:
        app: mcp-math-server
    spec:
      containers:
      - name: math
        image: python:3.11-slim
        command: ["/bin/sh", "-c"]
        args:
        - |
          pip install "mcp[cli]" uvicorn starlette && 
          python /app/server.py
        ports:
        - containerPort: 8000
        volumeMounts:
        - name: script-volume
          mountPath: /app
        readinessProbe:
          httpGet:
            path: /
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: script-volume
        configMap:
          name: mcp-math-script
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-math-server
  namespace: default
spec:
  selector:
    app: mcp-math-server
  ports:
  - port: 80
    targetPort: 8000
EOF
```

### Kube-Prometheus

```
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
```

```
helm install kube-prometheus -n monitoring prometheus-community/kube-prometheus-stack --create-namespace
```

Username: admin
Password: `kubectl get secret kube-prometheus-grafana -n monitoring -o jsonpath='{.data.admin-password}' | base64 --decode`


------------------------------------------------------------------------------------------------------------

## LLM Connectivity

```
kubectl apply -f- <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: anthropic-secret
  namespace: agentgateway-system
  labels:
    app: agentgateway-route
type: Opaque
stringData:
  Authorization: $ANTHROPIC_API_KEY
EOF
```

```
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: agentgateway-route
  namespace: agentgateway-system
  labels:
    app: agentgateway
spec:
  gatewayClassName: agentgateway
  listeners:
    - name: http
      port: 8080
      protocol: HTTP
      allowedRoutes:
        namespaces:
          from: Same
EOF
```

```
kubectl apply -f - <<EOF
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayBackend
metadata:
  labels:
    app: agentgateway-route
  name: anthropic
  namespace: agentgateway-system
spec:
  ai:
    provider:
        anthropic:
          model: "claude-3-5-haiku-latest"
  policies:
    auth:
      secretRef:
        name: anthropic-secret
EOF
```

```
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: claude
  namespace: agentgateway-system
  labels:
    app: agentgateway-route
spec:
  parentRefs:
    - name: agentgateway-route
      namespace: agentgateway-system
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
    - name: anthropic
      namespace: agentgateway-system
      group: agentgateway.dev
      kind: AgentgatewayBackend
EOF
```

```
export INGRESS_GW_ADDRESS=$(kubectl get svc -n agentgateway-system agentgateway-route -o jsonpath="{.status.loadBalancer.ingress[0]['hostname','ip']}")
echo $INGRESS_GW_ADDRESS
```

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

------------------------------------------------------------------------------------------------------------

## Observability

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
    app: agentgateway-route
    release: kube-prometheus
spec:
  namespaceSelector:
    matchNames:
      - agentgateway-system
  selector:
    matchLabels:
      gateway.networking.k8s.io/gateway-class-name: agentgateway
      #gateway.networking.k8s.io/gateway-name: agentgateway-route
  podMetricsEndpoints:
  - port: metrics
    path: /metrics
    interval: 30s
    scrapeTimeout: 10s
EOF
```

2. Run the `curl` again
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

3. Check the dashboard for metrics

```
kubectl --namespace monitoring port-forward svc/kube-prometheus-grafana 3000:80
```

To log into the Grafana UI:

1. Username: admin
2. Password: `kubectl get secret kube-prometheus-grafana -n monitoring -o jsonpath='{.data.admin-password}' | base64 --decode`

------------------------------------------------------------------------------------------------------------

## Rate Limiting

```
kubectl apply -f- <<EOF
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: anthropic-ratelimit
  namespace: agentgateway-system
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: claude
  traffic:
    rateLimit:
      local:
        - requests: 1
          unit: Minutes
EOF
```

Capture the LB IP of the service. This will be used later to send a request to the LLM.
```
export INGRESS_GW_ADDRESS=$(kubectl get svc -n agentgateway-system agentgateway-route -o jsonpath="{.status.loadBalancer.ingress[0]['hostname','ip']}")
echo $INGRESS_GW_ADDRESS
```

Run the `curl` below twice
```
curl "$INGRESS_GW_ADDRESS:8080/anthropic" -v \ -H content-type:application/json -H x-api-key:$ANTHROPIC_API_KEY -H "anthropic-version: 2023-06-01" -d '{
  "model": "claude-sonnet-4-5",
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

You'll see an output similar to the below:
```
* upload completely sent off: 292 bytes
< HTTP/1.1 429 Too Many Requests
< content-type: text/plain
< x-ratelimit-limit: 1
< x-ratelimit-remaining: 0
< x-ratelimit-reset: 21
< content-length: 19
< date: Tue, 06 Jan 2026 14:04:24 GMT
```

If you check the agentgateway Pod logs, you'll see the rate limit error.

```
kubectl logs -n agentgateway-system AGENTGATEWAY_POD --tail=50 | grep -i "request\|error\|anthropic"
```

```
2025-10-20T16:08:59.886579Z     info    request gateway=agentgateway listener=http route=gloo-system/claude src.addr=10.142.0.25:42187 http.method=POST http.host=34.148.15.158 http.path=/anthropic http.version=HTTP/1.1 http.status=429 error="rate limit exceeded" duration=0ms
```

------------------------------------------------------------------------------------------------------------

## Prompt Guards

```
kubectl apply -f - <<EOF
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: credit-guard-prompt-guard
  namespace: agentgateway-system
  labels:
    app: agentgateway
spec:
  targetRefs:
  - group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: claude
  backend:
    ai:
      promptGuard:
        request:
        - response:
            message: "Rejected due to inappropriate content"
          regex:
            action: REJECT
            matches:
            - "credit card"
EOF
```

```
curl "$INGRESS_GW_ADDRESS:8080/anthropic" -v -H content-type:application/json -H x-api-key:$ANTHROPIC_API_KEY -H "anthropic-version: 2023-06-01" -d '{
  "messages": [
    {
      "role": "system",
      "content": "You are a skilled cloud-native network engineer."
    },
    {
      "role": "user",
      "content": "What is a credit card?"
    }
  ]
}' | jq
```

------------------------------------------------------------------------------------------------------------

## MCP Auth

```
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: mcp-gateway
  namespace: agentgateway-system
  labels:
    app: mcp-gateway
spec:
  gatewayClassName: agentgateway
  listeners:
    - name: mcp
      port: 3000
      protocol: HTTP
      allowedRoutes:
        namespaces:
          from: Same
EOF
```

```
kubectl apply -f - <<EOF
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayBackend
metadata:
  name: demo-mcp-server
  namespace: agentgateway-system
spec:
  mcp:
    targets:
      - name: demo-mcp-server
        static:
          host: mcp-math-server.default.svc.cluster.local
          port: 8000
          path: /mcp
          protocol: StreamableHTTP
EOF
```

```
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: mcp-route
  namespace: agentgateway-system
  labels:
    app: mcp-gateway
spec:
  parentRefs:
    - name: mcp-gateway
  rules:
    - backendRefs:
      - name: demo-mcp-server
        namespace: agentgateway-system
        group: agentgateway.dev
        kind: AgentgatewayBackend
EOF
```

```
export GATEWAY_IP=$(kubectl get svc agentgateway -n gloo-system -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo $GATEWAY_IP
```

```
npx modelcontextprotocol/inspector#0.16.2
```

```
kubectl apply -f- <<EOF
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: jwt
  namespace: agentgateway-system
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: mcp-gateway
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

```
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InNvbG8tcHVibGljLWtleS0wMDEifQ.eyJpc3MiOiJzb2xvLmlvIiwib3JnIjoic29sby5pbyIsInN1YiI6ImJvYiIsInRlYW0iOiJvcHMiLCJleHAiOjIwNzQyNzQ5NTQsImxsbXMiOnsibWlzdHJhbGFpIjpbIm1pc3RyYWwtbGFyZ2UtbGF0ZXN0Il19fQ.GF_uyLpZSTT1DIvJeO_eish1WDjMaS4BQSifGQhqPRLjzu3nXtPkaBRjceAmJi9gKZYAzkT25MIrT42ZIe3bHilrd1yqittTPWrrM4sWDDeldnGsfU07DWJHyboNapYR-KZGImSmOYshJlzm1tT_Bjt3-RK3OBzYi90_wl0dyAl9D7wwDCzOD4MRGFpoMrws_OgVrcZQKcadvIsH8figPwN4mK1U_1mxuL08RWTu92xBcezEO4CdBaFTUbkYN66Y2vKSTyPCxg3fLtg1mvlzU1-Wgm2xZIiPiarQHt6Uq7v9ftgzwdUBQM1AYLvUVhCN6XkkR9OU3p0OXiqEDjAxcg
```

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
------------------------------------------------------------------------------------------------------------

## MCP + oAuth

https://github.com/AdminTurnedDevOps/agentic-demo-repo/tree/main/mcp/mcp-oauth-demos
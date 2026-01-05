#!/usr/bin/env python3
"""
Cloud Native Architecture MCP Server

An MCP server that provides tools to generate architecture diagrams for:
- Kubernetes clusters
- AWS infrastructure
- GCP infrastructure

Uses Diagrams library (diagrams.mingrammer.com) to create visual architecture diagrams.
"""

import asyncio
import json
from typing import Any
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import AnyUrl
import mcp.server.stdio

# Import diagrams library
from diagrams import Diagram, Cluster, Edge
from diagrams.k8s.clusterconfig import HPA
from diagrams.k8s.compute import Deployment, Pod, ReplicaSet, StatefulSet, DaemonSet, Job
from diagrams.k8s.network import Ingress, Service
from diagrams.k8s.storage import PV, PVC, StorageClass
from diagrams.k8s.podconfig import ConfigMap, Secret
from diagrams.aws.compute import EC2, ECS, EKS, Lambda
from diagrams.aws.database import RDS, Dynamodb, Elasticache, Redshift
from diagrams.aws.network import ELB, ALB, NLB, CloudFront, Route53, VPC
from diagrams.aws.storage import S3, EBS, EFS
from diagrams.aws.integration import SQS, SNS, Eventbridge
from diagrams.gcp.compute import GCE, GKE, ComputeEngine, Functions
from diagrams.gcp.database import SQL, Firestore, BigTable, Spanner
from diagrams.gcp.network import LoadBalancing, DNS, VPC as GCP_VPC
from diagrams.gcp.storage import GCS, PersistentDisk
from diagrams.gcp.analytics import BigQuery, Dataflow, Pubsub

import os
import base64
from pathlib import Path


# Create MCP server instance
server = Server("cloud-native-architecture-mcp")

# Diagram output directory
OUTPUT_DIR = Path("/tmp/architecture_diagrams")
OUTPUT_DIR.mkdir(exist_ok=True)


def parse_component_config(component_str: str) -> dict:
    """Parse component configuration from string format like 'deployment:my-app:3'"""
    parts = component_str.split(":")
    return {
        "type": parts[0] if len(parts) > 0 else "",
        "name": parts[1] if len(parts) > 1 else "unnamed",
        "replicas": int(parts[2]) if len(parts) > 2 else 1
    }


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available architecture diagram tools."""
    return [
        Tool(
            name="build-kubernetes-diagram",
            description="Generate a Kubernetes architecture diagram with deployments, services, ingress, storage, and other K8s resources. Supports namespace clustering and component connections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the diagram"
                    },
                    "components": {
                        "type": "array",
                        "description": "List of Kubernetes components to include",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "name": {"type": "string"},
                                "replicas": {"type": "number"}
                            },
                            "required": ["type", "name"]
                        }
                    },
                    "clusters": {
                        "type": "array",
                        "description": "Optional cluster groupings (namespaces)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "components": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                }
                            }
                        }
                    },
                    "connections": {
                        "type": "array",
                        "description": "Connections between components",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "label": {"type": "string"}
                            },
                            "required": ["from", "to"]
                        }
                    }
                },
                "required": ["name", "components"]
            }
        ),
        Tool(
            name="build-aws-diagram",
            description="Generate an AWS architecture diagram with compute, database, storage, networking, and integration services. Supports VPC groupings and component connections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the diagram"
                    },
                    "components": {
                        "type": "array",
                        "description": "List of AWS components to include",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "name": {"type": "string"}
                            },
                            "required": ["type", "name"]
                        }
                    },
                    "vpcs": {
                        "type": "array",
                        "description": "Optional VPC groupings",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "components": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                }
                            }
                        }
                    },
                    "connections": {
                        "type": "array",
                        "description": "Connections between components",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "label": {"type": "string"}
                            },
                            "required": ["from", "to"]
                        }
                    }
                },
                "required": ["name", "components"]
            }
        ),
        Tool(
            name="build-gcp-diagram",
            description="Generate a GCP architecture diagram with compute, database, storage, networking, and analytics services. Supports VPC/network groupings and component connections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the diagram"
                    },
                    "components": {
                        "type": "array",
                        "description": "List of GCP components to include",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "name": {"type": "string"}
                            },
                            "required": ["type", "name"]
                        }
                    },
                    "vpcs": {
                        "type": "array",
                        "description": "Optional VPC groupings",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "components": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                }
                            }
                        }
                    },
                    "connections": {
                        "type": "array",
                        "description": "Connections between components",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "label": {"type": "string"}
                            },
                            "required": ["from", "to"]
                        }
                    }
                },
                "required": ["name", "components"]
            }
        )
    ]


def get_k8s_component(comp_type: str, name: str):
    """Map component type to diagrams K8s class."""
    mapping = {
        "deployment": Deployment,
        "statefulset": StatefulSet,
        "daemonset": DaemonSet,
        "job": Job,
        "pod": Pod,
        "service": Service,
        "ingress": Ingress,
        "pvc": PVC,
        "pv": PV,
        "storageclass": StorageClass,
        "configmap": ConfigMap,
        "secret": Secret,
        "hpa": HPA,
        "replicaset": ReplicaSet
    }
    component_class = mapping.get(comp_type.lower())
    if component_class:
        return component_class(name)
    return None


def get_aws_component(comp_type: str, name: str):
    """Map component type to diagrams AWS class."""
    mapping = {
        "ec2": EC2,
        "ecs": ECS,
        "eks": EKS,
        "lambda": Lambda,
        "rds": RDS,
        "dynamodb": Dynamodb,
        "elasticache": Elasticache,
        "redshift": Redshift,
        "s3": S3,
        "ebs": EBS,
        "efs": EFS,
        "elb": ELB,
        "alb": ALB,
        "nlb": NLB,
        "cloudfront": CloudFront,
        "route53": Route53,
        "vpc": VPC,
        "sqs": SQS,
        "sns": SNS,
        "eventbridge": Eventbridge
    }
    component_class = mapping.get(comp_type.lower())
    if component_class:
        return component_class(name)
    return None


def get_gcp_component(comp_type: str, name: str):
    """Map component type to diagrams GCP class."""
    mapping = {
        "gce": GCE,
        "gke": GKE,
        "computeengine": ComputeEngine,
        "functions": Functions,
        "sql": SQL,
        "firestore": Firestore,
        "bigtable": BigTable,
        "spanner": Spanner,
        "loadbalancing": LoadBalancing,
        "dns": DNS,
        "vpc": GCP_VPC,
        "gcs": GCS,
        "persistentdisk": PersistentDisk,
        "bigquery": BigQuery,
        "dataflow": Dataflow,
        "pubsub": Pubsub
    }
    component_class = mapping.get(comp_type.lower())
    if component_class:
        return component_class(name)
    return None


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls for building architecture diagrams."""

    if name == "build-kubernetes-diagram":
        diagram_name = arguments.get("name", "k8s-architecture")
        components_config = arguments.get("components", [])
        clusters_config = arguments.get("clusters", [])
        connections_config = arguments.get("connections", [])

        output_file = OUTPUT_DIR / f"{diagram_name}"

        with Diagram(diagram_name, filename=str(output_file), show=False, direction="LR"):
            # Create component objects
            components = {}

            # Handle clusters
            if clusters_config:
                for cluster_config in clusters_config:
                    cluster_name = cluster_config.get("name", "Cluster")
                    cluster_component_names = cluster_config.get("components", [])

                    with Cluster(cluster_name):
                        for comp_config in components_config:
                            if comp_config["name"] in cluster_component_names:
                                comp = get_k8s_component(comp_config["type"], comp_config["name"])
                                if comp:
                                    components[comp_config["name"]] = comp

            # Create remaining components not in clusters
            for comp_config in components_config:
                if comp_config["name"] not in components:
                    comp = get_k8s_component(comp_config["type"], comp_config["name"])
                    if comp:
                        components[comp_config["name"]] = comp

            # Create connections
            for conn in connections_config:
                from_comp = components.get(conn["from"])
                to_comp = components.get(conn["to"])
                label = conn.get("label", "")

                if from_comp and to_comp:
                    if label:
                        from_comp >> Edge(label=label) >> to_comp
                    else:
                        from_comp >> to_comp

        # Read the generated image
        image_path = f"{output_file}.png"
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        return [
            TextContent(
                type="text",
                text=f"Kubernetes architecture diagram '{diagram_name}' created successfully with {len(components)} components."
            ),
            ImageContent(
                type="image",
                data=image_data,
                mimeType="image/png"
            )
        ]

    elif name == "build-aws-diagram":
        diagram_name = arguments.get("name", "aws-architecture")
        components_config = arguments.get("components", [])
        vpcs_config = arguments.get("vpcs", [])
        connections_config = arguments.get("connections", [])

        output_file = OUTPUT_DIR / f"{diagram_name}"

        with Diagram(diagram_name, filename=str(output_file), show=False, direction="LR"):
            components = {}

            # Handle VPCs
            if vpcs_config:
                for vpc_config in vpcs_config:
                    vpc_name = vpc_config.get("name", "VPC")
                    vpc_component_names = vpc_config.get("components", [])

                    with Cluster(vpc_name):
                        for comp_config in components_config:
                            if comp_config["name"] in vpc_component_names:
                                comp = get_aws_component(comp_config["type"], comp_config["name"])
                                if comp:
                                    components[comp_config["name"]] = comp

            # Create remaining components not in VPCs
            for comp_config in components_config:
                if comp_config["name"] not in components:
                    comp = get_aws_component(comp_config["type"], comp_config["name"])
                    if comp:
                        components[comp_config["name"]] = comp

            # Create connections
            for conn in connections_config:
                from_comp = components.get(conn["from"])
                to_comp = components.get(conn["to"])
                label = conn.get("label", "")

                if from_comp and to_comp:
                    if label:
                        from_comp >> Edge(label=label) >> to_comp
                    else:
                        from_comp >> to_comp

        # Read the generated image
        image_path = f"{output_file}.png"
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        return [
            TextContent(
                type="text",
                text=f"AWS architecture diagram '{diagram_name}' created successfully with {len(components)} components."
            ),
            ImageContent(
                type="image",
                data=image_data,
                mimeType="image/png"
            )
        ]

    elif name == "build-gcp-diagram":
        diagram_name = arguments.get("name", "gcp-architecture")
        components_config = arguments.get("components", [])
        vpcs_config = arguments.get("vpcs", [])
        connections_config = arguments.get("connections", [])

        output_file = OUTPUT_DIR / f"{diagram_name}"

        with Diagram(diagram_name, filename=str(output_file), show=False, direction="LR"):
            components = {}

            # Handle VPCs/Networks
            if vpcs_config:
                for vpc_config in vpcs_config:
                    vpc_name = vpc_config.get("name", "VPC")
                    vpc_component_names = vpc_config.get("components", [])

                    with Cluster(vpc_name):
                        for comp_config in components_config:
                            if comp_config["name"] in vpc_component_names:
                                comp = get_gcp_component(comp_config["type"], comp_config["name"])
                                if comp:
                                    components[comp_config["name"]] = comp

            # Create remaining components not in VPCs
            for comp_config in components_config:
                if comp_config["name"] not in components:
                    comp = get_gcp_component(comp_config["type"], comp_config["name"])
                    if comp:
                        components[comp_config["name"]] = comp

            # Create connections
            for conn in connections_config:
                from_comp = components.get(conn["from"])
                to_comp = components.get(conn["to"])
                label = conn.get("label", "")

                if from_comp and to_comp:
                    if label:
                        from_comp >> Edge(label=label) >> to_comp
                    else:
                        from_comp >> to_comp

        # Read the generated image
        image_path = f"{output_file}.png"
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        return [
            TextContent(
                type="text",
                text=f"GCP architecture diagram '{diagram_name}' created successfully with {len(components)} components."
            ),
            ImageContent(
                type="image",
                data=image_data,
                mimeType="image/png"
            )
        ]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def async_main():
    """Run the MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Entry point for the MCP server."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
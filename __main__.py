"""A Python Pulumi program"""

import pulumi
import pulumi_gcp as gcp

config = pulumi.Config()
gcp_config = pulumi.Config("gcp")
stack = pulumi.get_stack()

project_id = gcp_config.require("project")
region = gcp_config.require("region")

db_type = config.get("db_type") or "postgres"
db_host = config.get("db_host") or "pg-dsv.rizaasset.com"
db_port = config.get("db_port") or "15432"
db_name = config.get("db_name") or "metabase"
db_user = config.get_secret("db_user") or "riza-dsv"
db_pass = config.get_secret("db_pass") or "riza-dsv"

vpc_connector_name = config.get("vpc_connector_name")
vpc_network = config.get("vpc_network") or "default"
vpc_subnet = config.get("vpc_subnet")
vpc_egress = config.get("vpc_egress") or "ALL_TRAFFIC"

cpu_limit = config.get("cpu_limit") or "2"
memory_limit = config.get("memory_limit") or "4Gi"
min_instances = config.get_int("min_instances") or 0
max_instances = config.get_int("max_instances") or 3
request_timeout = config.get_int("request_timeout") or 300
startup_cpu_boost = config.get_bool("startup_cpu_boost")
if startup_cpu_boost is None:
    startup_cpu_boost = True
allow_unauthenticated = config.get_bool("allow_unauthenticated")
if allow_unauthenticated is None:
    allow_unauthenticated = True

cloud_run_api = gcp.projects.Service(
    "cloud-run-api",
    service="run.googleapis.com",
    disable_on_destroy=False,
)

vpc_access_api = gcp.projects.Service(
    "vpcaccess-api",
    service="vpcaccess.googleapis.com",
    disable_on_destroy=False,
)

compute_api = gcp.projects.Service(
    "compute-api",
    service="compute.googleapis.com",
    disable_on_destroy=False,
)

vpc_connector = None
vpc_access_args = None

if vpc_connector_name:
    if vpc_subnet:
        vpc_connector = gcp.vpcaccess.Connector(
            "vpc-connector",
            name=vpc_connector_name,
            region=region,
            network=vpc_network,
            ip_cidr_range="10.8.0.0/28",
            max_instances=3,
            min_instances=2,
            subnet=gcp.vpcaccess.ConnectorSubnetArgs(
                name=vpc_subnet,
                project_id=project_id,
            ),
            opts=pulumi.ResourceOptions(depends_on=[vpc_access_api, compute_api]),
        )
    else:
        vpc_connector = gcp.vpcaccess.Connector(
            "vpc-connector",
            name=vpc_connector_name,
            region=region,
            network=vpc_network,
            ip_cidr_range="10.8.0.0/28",
            max_instances=10,
            min_instances=2,
            opts=pulumi.ResourceOptions(depends_on=[vpc_access_api, compute_api]),
        )

    vpc_access_args = gcp.cloudrunv2.ServiceTemplateVpcAccessArgs(
        connector=vpc_connector.id,
        egress=vpc_egress,
    )

env_vars = [
    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
        name="MB_DB_TYPE",
        value=db_type,
    ),
    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
        name="MB_DB_DBNAME",
        value=db_name,
    ),
    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
        name="MB_DB_PORT",
        value=db_port,
    ),
    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
        name="MB_DB_USER",
        value=db_user,
    ),
    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
        name="MB_DB_PASS",
        value=db_pass,
    ),
    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
        name="MB_DB_HOST",
        value=db_host,
    ),
]

metabase_service = gcp.cloudrunv2.Service(
    "metabase-service",
    name="metabase",
    location=region,
    template=gcp.cloudrunv2.ServiceTemplateArgs(
        vpc_access=vpc_access_args,
        containers=[
            gcp.cloudrunv2.ServiceTemplateContainerArgs(
                image="metabase/metabase:latest",
                ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
                    container_port=3000,
                ),
                resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                    limits={
                        "cpu": cpu_limit,
                        "memory": memory_limit,
                    },
                    cpu_idle=False,
                    startup_cpu_boost=startup_cpu_boost,
                ),
                startup_probe=gcp.cloudrunv2.ServiceTemplateContainerStartupProbeArgs(
                    initial_delay_seconds=30,
                    timeout_seconds=240,
                    period_seconds=240,
                    failure_threshold=10,
                    tcp_socket=gcp.cloudrunv2.ServiceTemplateContainerStartupProbeTcpSocketArgs(
                        port=3000,
                    ),
                ),
                envs=env_vars,
            )
        ],
        scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(
            min_instance_count=min_instances,
            max_instance_count=max_instances,
        ),
        timeout=f"{request_timeout}s",
    ),
    traffics=[
        gcp.cloudrunv2.ServiceTrafficArgs(
            type="TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
            percent=100,
        )
    ],
    opts=pulumi.ResourceOptions(
        depends_on=[cloud_run_api, vpc_access_api]
        + ([vpc_connector] if vpc_connector else [])
    ),
)

if allow_unauthenticated:
    public_access = gcp.cloudrunv2.ServiceIamMember(
        "public-access",
        name=metabase_service.name,
        location=metabase_service.location,
        role="roles/run.invoker",
        member="allUsers",
    )

pulumi.export("service_name", metabase_service.name)
pulumi.export("service_url", metabase_service.uri)
pulumi.export("service_location", metabase_service.location)
pulumi.export("project_id", project_id)
pulumi.export("service_id", metabase_service.id)
if vpc_connector:
    pulumi.export("vpc_connector_id", vpc_connector.id)
    pulumi.export("vpc_connector_name", vpc_connector.name)

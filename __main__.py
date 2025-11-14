"""A Python Pulumi program"""

import pulumi
import pulumi_gcp as gcp

config = pulumi.Config()
gcp_config = pulumi.Config("gcp")

project_id = gcp_config.require("project")
region = config.get("region") or "us-central1"

db_type = config.get("db_type") or "postgres"
db_host = config.get("db_host") or "pg-dsv.rizaasset.com"
db_port = config.get("db_port") or "15432"
db_name = config.get("db_name") or "metabase"
db_user = config.get_secret("db_user") or "riza-dsv"
db_pass = config.get_secret("db_pass") or "riza-dsv"

vpc_connector_name = gcp_config.get("vpc_connector_name")
vpc_egress = gcp_config.get("vpc_egress") or "PRIVATE_RANGES_ONLY"

cpu_limit = config.get("cpu_limit") or "2"
memory_limit = config.get("memory_limit") or "4Gi"
min_instances = config.get_int("min_instances") or 0
max_instances = config.get_int("max_instances") or 3

cloud_run_api = gcp.projects.Service(
    "cloud-run-api",
    service="run.googleapis.com",
    disable_on_destroy=False,
)

vpc_connector = None
vpc_access_args = None

if vpc_connector_name:
    vpc_access_api = gcp.projects.Service(
        "vpcaccess-api",
        service="vpcaccess.googleapis.com",
        disable_on_destroy=False,
    )

    vpc_connector = gcp.vpcaccess.get_connector(
        name=vpc_connector_name,
        region=region,
        project=project_id,
    )

    vpc_access_args = gcp.cloudrunv2.ServiceTemplateVpcAccessArgs(
        connector=vpc_connector.id,
        egress=vpc_egress,
    )

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
                ),
                envs=[
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
                ],
            )
        ],
        scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(
            min_instance_count=min_instances,
            max_instance_count=max_instances,
        ),
    ),
    traffics=[
        gcp.cloudrunv2.ServiceTrafficArgs(
            type="TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
            percent=100,
        )
    ],
    opts=pulumi.ResourceOptions(
        depends_on=[cloud_run_api] + ([vpc_access_api] if vpc_connector_name else [])
    ),
)

iam_binding = gcp.cloudrunv2.ServiceIamMember(
    "metabase-public-access",
    name=metabase_service.name,
    location=metabase_service.location,
    role="roles/run.invoker",
    member="allUsers",
)

pulumi.export("service_url", metabase_service.uri)
pulumi.export("service_name", metabase_service.name)
pulumi.export("service_location", metabase_service.location)
pulumi.export("project_id", project_id)
if vpc_connector:
    pulumi.export("vpc_connector", vpc_connector.id)

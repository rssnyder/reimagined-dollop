from os import getenv
from re import sub

from requests import get, put, post, delete, exceptions, Session
from requests.adapters import HTTPAdapter, Retry

s = Session()

retries = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])

s.mount("http://", HTTPAdapter(max_retries=retries))

spacing = "\t\t"


def get_all_cc() -> list:
    # get all the cc in an account

    resp = s.get(
        "https://app.harness.io/ccm/api/business-mapping",
        params={
            "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
        },
        headers={
            "Content-Type": "application/json",
            "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
        },
    )

    resp.raise_for_status()

    return resp.json().get("resource", {}).get("businessMappings", [])


class CloudAccount:
    def __init__(
        self,
        cloud: str,
        identifier: str,
        domain: str,
        bu: str,
    ):
        cloud_fmt = cloud.lower()
        if cloud_fmt not in ["aws", "azure", "gcp"]:
            raise Exception(f"Unknown cloud {cloud}")

        self.cloud = cloud_fmt
        self.identifier = identifier
        self.bu = bu
        self.domain = domain

        self.connector_id = f"{self.cloud}{sub('[^0-9a-zA-Z]+', '_', self.identifier)}"

    def __repr__(self):
        return f"{self.cloud},{self.identifier},{self.domain},{self.bu}"

    def create_connector(
        self,
        role_name: str,
        tenant_id: str,
        service_account_email: str,
        dry_run: bool = False,
    ):
        if self.identifier == self.payer_id:
            return f"CONNECTOR:skipped{spacing}{self.name} seems to be a payer account, skipping"

        payload = {
            "connector": {
                "name": self.name,
                "identifier": self.connector_id,
                "tags": {},
                "spec": {},
                "type": "",
            },
        }

        if self.cloud == "aws":
            payload["connector"]["type"] = "CEAws"
            payload["connector"]["spec"] = {
                "crossAccountAccess": {
                    "crossAccountRoleArn": f"arn:aws:iam::{self.identifier}:role/{role_name}",
                    "externalId": f'harness:891928451355:{getenv("HARNESS_ACCOUNT_ID")}',
                },
                "curAttributes": None,
                "awsAccountId": self.identifier,
                "isAWSGovCloudAccount": False,
                "featuresEnabled": [
                    "GOVERNANCE",
                    "VISIBILITY",
                ],
            }
        elif self.cloud == "azure":
            payload["connector"]["type"] = "CEAzure"
            payload["connector"]["spec"] = {
                "tenantId": tenant_id,
                "subscriptionId": self.identifier,
                "featuresEnabled": [
                    "GOVERNANCE",
                    "VISIBILITY",
                ],
            }
        elif self.cloud == "gcp":
            payload["connector"]["type"] = "GcpCloudCost"
            payload["connector"]["spec"] = {
                "serviceAccountEmail": service_account_email,
                "projectId": self.identifier,
                "featuresEnabled": [
                    "GOVERNANCE",
                    "VISIBILITY",
                ],
            }
        else:
            raise Exception(f"Unknown cloud {cloud}")

        if dry_run:
            return payload
        else:
            # check if the connector already exists in harness
            resp = s.get(
                f"https://app.harness.io/ng/api/connectors/{payload['connector']['identifier']}",
                params={
                    "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
                    "routingId": getenv("HARNESS_ACCOUNT_ID"),
                },
                headers={
                    "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
                },
            )

            # update connector
            if resp.status_code == 200:
                status = resp.json().get("data", {}).get("status", {}).get("status")
                if status == "FAILURE":
                    status += ": " + str(
                        [
                            x.get("message")
                            for x in resp.json()
                            .get("data", {})
                            .get("status", {})
                            .get("errors", [])
                        ]
                    )

                resp = s.put(
                    "https://app.harness.io/gateway/ng/api/connectors",
                    params={
                        "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
                        "routingId": getenv("HARNESS_ACCOUNT_ID"),
                    },
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
                    },
                    json=payload,
                )

                if resp.status_code == 200:
                    return f"CONNECTOR:updated{spacing}{self.connector_id}{spacing}STATUS{spacing}{status}"
                else:
                    return f"CONNECTOR:UPDATE_ERROR{spacing}{resp.text}"

            # create connector
            else:
                resp = s.post(
                    "https://app.harness.io/gateway/ng/api/connectors",
                    params={
                        "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
                        "routingId": getenv("HARNESS_ACCOUNT_ID"),
                    },
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
                    },
                    json=payload,
                )

            if resp.status_code == 200:
                return f"CONNECTOR:created{spacing}{self.connector_id}"
            else:
                return f"\nCONNECTOR:CREATE_ERROR{spacing}{resp.text}\n"

    def delete_connector(self):
        resp = s.delete(
            f"https://app.harness.io/ng/api/connectors/{self.connector_id}",
            params={
                "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
                "routingId": getenv("HARNESS_ACCOUNT_ID"),
            },
            headers={
                "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
            },
        )

        if resp.status_code == 200:
            return resp.json()
        else:
            return resp.text


class CostCatagory:
    def __init__(self, name: str):
        self.name = name
        self.uuid = self.get_cc().get("uuid")
        self.buckets = []

    def __repr__(self):
        result = self.name
        result += f"\n\nNumber of buckets: {len(self.buckets)}\n\n"
        clouds = {"aws": 0, "gcp": 0, "azure": 0}
        for bucket in self.buckets:
            result += "\n" + str(bucket)
            clouds["aws"] += len(bucket.aws)
            clouds["azure"] += len(bucket.azure)
            clouds["gcp"] += len(bucket.gcp)

        result += (
            f"\n\nAWS: {clouds['aws']}\nAzure: {clouds['azure']}\nGCP: {clouds['gcp']}"
        )
        return result

    def add(self, bucket_name: str, new: CloudAccount):
        # check bucket exists and add
        if not [
            x.add(new.cloud, new.identifier)
            for x in self.buckets
            if x.name == bucket_name
        ]:
            self.buckets.append(Bucket(bucket_name).add(new.cloud, new.identifier))

        return bucket_name

    def get_cc(self) -> dict:
        try:
            return [x for x in get_all_cc() if x["name"] == self.name].pop()
        except IndexError:
            return {}

    def update(self):
        if self.get_cc().get("uuid"):
            resp = s.put(
                "https://app.harness.io/gateway/ccm/api/business-mapping",
                params={
                    "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
                },
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
                },
                json={
                    "accountId": getenv("HARNESS_ACCOUNT_ID"),
                    "name": self.name,
                    "uuid": self.uuid,
                    "costTargets": [x.payload() for x in self.buckets if x],
                    "unallocatedCost": {
                        "strategy": "DISPLAY_NAME",
                        "label": "Unattributed",
                        "sharingStrategy": None,
                        "splits": None,
                    },
                    "dataSources": ["AWS"],
                },
            )

            try:
                resp.raise_for_status()
            except exceptions.HTTPError:
                return resp.text

            return resp.json()


class Bucket:
    def __init__(self, name: str):
        self.name = name
        self.aws = []
        self.azure = []
        self.gcp = []

    def __repr__(self):
        result = "\n" + self.name
        result += "\nAWS: " + str(self.aws)
        result += "\nAzure: " + str(self.azure)
        result += "\nGCP: " + str(self.gcp)

        return result

    def add(self, cloud: str, identifier: str):
        if cloud == "aws":
            self.aws.append(identifier)
        elif cloud == "azure":
            self.azure.append(identifier)
        elif cloud == "gcp":
            self.gcp.append(identifier)
        else:
            raise Exception(f"Unknown cloud {self.cloud}")

        return self

    def __len__(self):
        return len(self.aws) + len(self.azure) + len(self.gcp)

    def payload(self):
        payload = {
            "name": self.name,
            "rules": [],
        }

        if self.aws:
            payload["rules"].append(
                {
                    "viewConditions": [
                        {
                            "type": "VIEW_ID_CONDITION",
                            "viewField": {
                                "fieldId": "awsUsageaccountid",
                                "fieldName": "Account",
                                "identifier": "AWS",
                                "identifierName": "AWS",
                            },
                            "viewOperator": "IN",
                            "values": self.aws,
                        }
                    ]
                }
            )

        if self.azure:
            payload["rules"].append(
                {
                    "viewConditions": [
                        {
                            "type": "VIEW_ID_CONDITION",
                            "viewField": {
                                "fieldId": "azureSubscriptionGuid",
                                "fieldName": "azureSubscriptionGuid",
                                "identifier": "AZURE",
                                "identifierName": "Azure",
                            },
                            "viewOperator": "IN",
                            "values": self.azure,
                        }
                    ]
                }
            )
        if self.gcp:
            payload["rules"].append(
                {
                    "viewConditions": [
                        {
                            "type": "VIEW_ID_CONDITION",
                            "viewField": {
                                "fieldId": "gcpProjectId",
                                "fieldName": "Project",
                                "identifier": "GCP",
                                "identifierName": "GCP",
                            },
                            "viewOperator": "IN",
                            "values": self.gcp,
                        }
                    ]
                }
            )

        return payload

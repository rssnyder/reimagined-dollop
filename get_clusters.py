from os import getenv
from sys import argv
from csv import reader

from google.cloud import resourcemanager_v3
from google.cloud import container_v1
from google.auth import default
from requests import get, post, put

from common import get_all_cc

# from test import get_test_clusters, get_test_connectors


class Cluster:
    def __init__(
        self,
        name: str,
        connector: str,
        bu: str,
    ):
        self.name = name
        self.connector = connector
        self.bu = bu


def get_projects(parent: str):
    client = resourcemanager_v3.ProjectsClient()

    resp = client.list_projects(
        request=resourcemanager_v3.ListProjectsRequest(
            parent=parent,
        )
    )

    projects = [x.project_id for x in resp]

    for folder in get_folders(parent):
        projects += get_projects(folder)

    return projects


def get_folders(parent: str):
    client = resourcemanager_v3.FoldersClient()

    resp = client.list_folders(
        request=resourcemanager_v3.ListFoldersRequest(
            parent=parent,
        )
    )

    return [x.name for x in resp]


def get_clusters(credentials, project_id: str):
    client = container_v1.ClusterManagerClient(credentials=credentials)

    clusters = client.list_clusters(parent=f"projects/{project_id}/locations/-")

    return clusters.clusters


def get_connectors(kind: str, pageIndex: int = 0):
    resp = post(
        "https://app.harness.io/gateway/ng/api/connectors/listV2",
        params={
            "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
            "pageSize": 50,
            "pageIndex": pageIndex,
        },
        headers={
            "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
        },
        json={"types": [kind], "filterType": "Connector"},
    )

    connectors = []
    if resp.status_code == 200:
        connectors += resp.json().get("data", {}).get("content", [])

        if resp.json().get("data", {}).get("totalPages") > pageIndex:
            connectors += get_connectors(kind, pageIndex + 1)
    else:
        print(resp.text)
        return []

    return connectors


def find_matches(connectors: list, clusters: list):
    results = []

    for connector in connectors:
        matches = [
            cluster
            for cluster in clusters
            if cluster[0].replace("_", "").replace("-", "")
            in connector.replace("_", "").replace("-", "")
        ]

        if not matches:
            print("!! no cluster found for", connector)
        elif len(matches) > 1:
            print("!! multiple clusters found for", connector)
        else:
            cluster = matches.pop()
            print(f"{connector}:\t\t{str(cluster)}")
            results.append(Cluster(cluster[0], connector, cluster[1]))

    return results


if __name__ == "__main__":
    # program arguments
    if len(argv) < 3:
        print(f"usage: {argv[0]} [BU Cluster CC Name][csv]")
        exit(1)

    bu_cluster_cc_name = argv[1]
    csv_file = argv[2]

    # get cost center id
    bu_cluster_cc_uuid = (
        [x for x in get_all_cc() if x["name"] == bu_cluster_cc_name].pop().get("uuid")
    )

    # get project->bu mapping
    project_bus = {}
    bus = []
    with open(csv_file, "r") as cc_data:
        datareader = reader(cc_data)
        next(datareader)

        for row in datareader:
            project_bus[row[0]] = row[2]
            bus.append(row[2])
    bus_set = set(bus)

    # get ccm k8s connector
    cluster_connectors = [
        x.get("connector", {}).get("name") for x in get_connectors("CEK8sCluster")
    ]
    # cluster_connectors = get_test_connectors()

    # log into gcp
    credentials, project_id = default()

    # get all clusters in all projects, tied to a bu
    clusters = []
    for project_id in get_projects(f"organizations/{getenv('GCP_ORG_ID')}"):
        clusters += [
            (x.name, project_bus[project_id])
            for x in get_clusters(credentials, project_id)
        ]
    # clusters = get_test_clusters()

    # match connectors to clusters
    cluster_obj = find_matches(cluster_connectors, clusters)

    # update cost catagory
    cost_targets = []
    for bu in bus_set:
        bu_cluster_connectors = [x.connector for x in cluster_obj if x.bu == bu]
        if not bu_cluster_connectors:
            continue

        cost_targets.append(
            {
                "name": bu,
                "rules": [
                    {
                        "viewConditions": [
                            {
                                "type": "VIEW_ID_CONDITION",
                                "viewField": {
                                    "fieldId": "clusterName",
                                    "fieldName": "Cluster Name",
                                    "identifierName": "Cluster",
                                    "identifier": "CLUSTER",
                                },
                                "viewOperator": "IN",
                                "values": bu_cluster_connectors,
                            }
                        ]
                    }
                ],
            }
        )

    resp = put(
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
            "name": bu_cluster_cc_name,
            "uuid": bu_cluster_cc_uuid,
            "costTargets": cost_targets,
            "unallocatedCost": {
                "strategy": "HIDE",
                "label": "Unattributed",
                "sharingStrategy": None,
                "splits": None,
            },
        },
    )

    print(resp.text)

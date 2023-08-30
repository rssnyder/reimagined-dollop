from os import getenv

from google.cloud import resourcemanager_v3

# # Create a client
# client = resourcemanager_v3.ProjectsClient()

# # Make the request
# page_result = client.list_projects(
#     request=resourcemanager_v3.ListProjectsRequest(
#         # parent="organizations/id",
#         parent=sales
#     )
# )

# # Handle the response
# for response in page_result:
#     print(response)

from google.cloud import container_v1
from google.auth import default
from requests import get, post


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


def get_connectors(kind: str):
    resp = post(
        "https://app.harness.io/gateway/ng/api/connectors/listV2",
        params={
            "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
        },
        headers={
            "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
        },
        json={"types": [kind], "filterType": "Connector"},
    )

    if resp.status_code == 200:
        return resp.json().get("data", {}).get("content", [])
    else:
        print(resp.text)
        return []


def find_matches(connectors: list, clusters: list):
    for connector in connectors:
        matches = [
            x
            for x in clusters
            if connector.replace("_", "").startswith(
                x.replace("_", "").replace("-", "")
            )
        ]
        if matches:
            print(f"{connector}: {str(matches)}")


if __name__ == "__main__":
    cluster_connectors = [
        x.get("connector", {}).get("name") for x in get_connectors("CEK8sCluster")
    ]

    print("harness ccm k8s connectors")
    print(cluster_connectors)

    credentials, project_id = default()

    clusters = []
    for project_id in get_projects(f"organizations/{getenv('GCP_ORG_ID')}"):
        clusters += [x.name for x in get_clusters(credentials, project_id)]

    print("gke clusters")
    print(clusters)

    # find_matches(cluster_connectors, clusters)

from csv import reader
from os import getenv
from sys import argv
from time import sleep
import json

from requests import put

from common import CloudAccount, CostCatagory


if __name__ == "__main__":
    # program arguments
    if len(argv) < 4:
        print(f"usage: {argv[0]} [domain cc name] [bu cc name] [csv]")
        exit(1)

    domain_cc_name = argv[1]
    bu_cc_name = argv[2]
    files = argv[3:]

    # storage for different clouds
    domains = CostCatagory(domain_cc_name)
    bus_obj = CostCatagory(bu_cc_name)
    bus = {}

    # loop through file and pull in account information
    for file_csv in files:
        with open(file_csv, "r") as cc_data:
            datareader = reader(cc_data)
            next(datareader)

            for row in datareader:
                # create instance of account with given data
                account = CloudAccount("gcp", row[0], row[1], row[2])

                # build bu->domain relationships
                if account.bu in bus:
                    bus[account.bu].add(account.domain)
                else:
                    bus[account.bu] = set([account.domain])

                domains.add(account.domain, account)

    print(domains.update())
    domains_uuid = domains.get_cc().get("uuid")

    print("bu->domain mappings:", str(bus))

    bu_buckets = []
    for bu in bus:
        bu_buckets.append(
            {
                "name": bu,
                "rules": [
                    {
                        "viewConditions": [
                            {
                                "type": "VIEW_ID_CONDITION",
                                "viewField": {
                                    "fieldId": domains.get_cc().get("uuid"),
                                    "fieldName": domains.name,
                                    "identifierName": "Cost Categories",
                                    "identifier": "BUSINESS_MAPPING",
                                },
                                "viewOperator": "IN",
                                "values": list(bus[bu]),
                            }
                        ]
                    }
                ],
            }
        )

    payload = {
        "accountId": getenv("HARNESS_ACCOUNT_ID"),
        "name": bu_cc_name,
        "uuid": bus_obj.get_cc().get("uuid"),
        "costTargets": bu_buckets,
        "sharedCosts": [],
        "unallocatedCost": {"label": "Unattributed", "strategy": "DISPLAY_NAME"},
    }

    resp = put(
        "https://app.harness.io/gateway/ccm/api/business-mapping",
        params={
            "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
        },
        headers={
            "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
        },
        json=payload,
    )

    if resp.status_code == 200:
        print(resp.json())
    else:
        print(resp.text)

from csv import reader
from os import getenv
from sys import argv
from time import sleep

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
    bus = CostCatagory(bu_cc_name)

    # loop through file and pull in account information
    for file_csv in files:
        with open(file_csv, "r") as cc_data:
            datareader = reader(cc_data)
            next(datareader)

            for row in datareader:

                # create instance of account with given data
                account = CloudAccount("gcp", row[0], row[1], row[2])

                domains.add(account.domain, account)
                bus.add(account.bu, account)

    print(domains.update())
    print(bus.update())

    sleep(5)

    print("Here is what we did...")

    sleep(5)

    print(domains)
    print()
    print(bus)

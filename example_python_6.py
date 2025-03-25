import json

from django.core.management.base import BaseCommand
from django.db import transaction
from mvp.models import Geography


class Command(BaseCommand):
    help = "Imports geography data from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "jurisdictions_file",
            type=str,
            help="Path to the jurisdictions file.",
        )

        parser.add_argument(
            "jurisdictions_info_file",
            type=str,
            help="Path to the jurisdictions info file.",
        )

        parser.add_argument(
            "--erase",
            action="store_true",
            help="Erase all existing geographies before importing.",
        )

    def handle(self, *args, **kwargs):
        # ask the user if they want to continue only when geography is not empty
        geography_count = Geography.objects.count()
        if geography_count != 0:
            self.stdout.write(f"Geography table contains {geography_count} records.")
            if kwargs["erase"]:
                self.stdout.write(
                    self.style.WARNING("All existing Geography data will be erased.")
                )
            confirm = input("Do you want to continue ? (y/N) ")
            if confirm.lower() != "y":
                self.stdout.write("Aborting")
                return

        jurisdictions_file = kwargs["jurisdictions_file"]
        jurisdiction_info_file = kwargs["jurisdictions_info_file"]

        with open(jurisdictions_file, "r") as f:
            data = json.load(f)

        with open(jurisdiction_info_file, "r") as f:
            info_data = json.load(f)

        if kwargs["erase"]:
            Geography.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("All previous records deleted."))

        self.create_geography_nodes(data, info_data)
        self.stdout.write(self.style.SUCCESS("Geography data imported successfully"))

    @transaction.atomic()
    def create_geography_nodes(self, data, info_data, parent=None):
        if parent is None:
            parent = Geography.add_root(name="All", code="all")
        for name, children in data.items():
            code = info_data.get(name, {}).get("iso3", name.lower())
            node = parent.add_child(name=name.title(), code=code)
            if isinstance(children, dict):
                self.create_geography_nodes(children, info_data, parent=node)


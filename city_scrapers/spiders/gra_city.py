from city_scrapers_core.constants import COMMISSION, COMMITTEE

from city_scrapers.mixins.gra_city import GrandRapidsCityMixin

spider_configs = [
    {
        "class_name": "GraPublicSafetySpider",
        "name": "gra_public_safety",
        "agency": "Grand Rapids Public Safety Committee",
        "keyword": "Public-Safety-Committee",
        "committee_id": 1,
        "classification": COMMITTEE,
    },
    {
        "class_name": "GraMobileGrSpider",
        "name": "gra_mobile_gr",
        "agency": "Grand Rapids Mobile GR Commission",
        "keyword": "Mobile-GR-Commission",
        "committee_id": 15,
        "classification": COMMISSION,
    },
    {
        "class_name": "GraCityCommissionSpider",
        "name": "gra_city_commission",
        "agency": "Grand Rapids City Commission",
        "keyword": "City-Commission-Meeting",
        "committee_id": 1,
        "classification": COMMISSION,
    },
]


def create_spiders():
    """
    Dynamically create spider classes using the spider_configs list
    and register them in the global namespace.
    """
    for config in spider_configs:
        class_name = config["class_name"]

        if class_name not in globals():
            # Build attributes dict without class_name to avoid duplication.
            # We make sure that the class_name is not already in the global namespace
            # Because some scrapy CLI commands like `scrapy list` will inadvertently
            # declare the spider class more than once otherwise
            attrs = {k: v for k, v in config.items() if k != "class_name"}

            # Dynamically create the spider class
            spider_class = type(
                class_name,
                (GrandRapidsCityMixin,),
                attrs,
            )

            # Register the class in the global namespace using its class_name
            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()

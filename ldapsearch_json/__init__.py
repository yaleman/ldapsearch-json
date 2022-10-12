""" connects to the given LDAP server and dumps the results out """

import json
import ssl
from typing import Any, Dict, List, Optional

from ldap3 import ALL, Connection, Server, Tls
from ldap3.core.exceptions import LDAPBindError
from loguru import logger
import typer

app = typer.Typer()

FILTER = "(objectClass=*)"
SEARCH_ATTRIBUTES_DEFAULT = ['*']

def cleandict(data: Dict[str, Any]) -> Dict[str,Any]:
    """ cleans a dict, turning single-entry lists into strings """
    if not data:
        return data
    retval = {}
    for key in data:
        if isinstance(data[key], (tuple, list)):
            # single object? just make it the value
            if len(data[key]) == 1:
                retval[key] = data[key][0]
        elif isinstance(data[key], dict):
            retval[key] = cleandict(data[key])
        else:
            retval[key] = data[key]
    return retval

#pylint: disable=too-many-arguments
def cli(
    server: str,
    base: str,
    filter_string: str = typer.Option(FILTER, "--filter", "-f"),
    search_attributes: List[str] = typer.Option(SEARCH_ATTRIBUTES_DEFAULT, "--search-attributes", "-s" ),
    username: Optional[str]=None,
    password: Optional[str]=None,
    ) -> None:
    """ JSON-dumping terrible knockoff of ldapsearch """
    if not search_attributes:
        search_attributes = SEARCH_ATTRIBUTES_DEFAULT

    tls_configuration = Tls(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLSv1_2)
    ldap_server = Server(server, use_ssl=True, get_info=ALL, tls=tls_configuration)
    try:
        with Connection(ldap_server,user=username, password=password) as conn:
            logger.debug("Doing search on base {} filter {} attributes {}", base, filter_string, search_attributes)
            conn.search(search_base=base, search_filter=filter_string, attributes=search_attributes)

            for entry in conn.entries:
                try:
                    data = json.loads(entry.entry_to_json())
                except json.JSONDecodeError as json_error:
                    logger.error("Failed to parse JSON for entry {}: {}", entry, json_error)
                cleaned_data = cleandict(data)
                print(json.dumps(cleaned_data, ensure_ascii=False))
    except LDAPBindError as error:
        logger.error("Failed to connect: {}", error)

import asyncio
import json
import ssl

import requests
from requests.auth import HTTPBasicAuth

from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

import websockets
from bs4 import BeautifulSoup as bs
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

opts = Options()
opts.headless = True

with open("rune_data.json", "r") as f:
    RUNE_DICT = json.load(f)


class runechanger:
    def __init__(self):
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.SUB_CHAMP_SELECT_SESSION_EVENT = json.dumps([5, "OnJsonApiEvent_lol-champ-select_v1_session"])
        self.out = "/Applications/League of Legends.app/Contents/LoL/lockfile"

        with open(self.out, 'r') as f:
            data = f.readline().strip().split(":")
        self.port = data[2]
        self.password = data[3]
        self.scheme = data[4]

        self.url = f"wss://riot:{self.password}@127.0.0.1:{str(self.port)}"

        self.player_pos = None
        self.phase = None
        self.champ_id = None
        self.assigned_role = None
        self.is_final_pick = None
        self.new_champ = (None, None)
        self.role_or_aram = None
        self.runes = {"primary_runes": None,
                      "secondary_runes": None,
                      "fragments": None}

    async def listener(self):
        async with websockets.connect(self.url, ssl=self.ssl_context) as websocket:
            await websocket.send(self.SUB_CHAMP_SELECT_SESSION_EVENT)
            while True:
                resp = await websocket.recv()
                if resp.strip():
                    response = json.loads(resp)
                    if response[2]['eventType'] == "Update":
                        self.__parse_response(response)
                        
                        try:
                            champ_name = self.__get_champ_name()[1]
                        except:
                            continue

                        if self.new_champ != (champ_name, self.assigned_role):
                            self.new_champ = (champ_name, self.assigned_role)
                            self.__prepare_driver(champ_name.lower())
                        if self.is_final_pick:
                            self.scrapeUGG()
                            self.set_runes()

    def set_runes(self):
        base_url = f"{self.scheme}://127.0.0.1:{self.port}"
        auth_header = HTTPBasicAuth('riot', self.password)
        page_id = self.__get_page_id(base_url, auth_header)["id"]
        url = f"{base_url}/lol-perks/v1/pages/{str(page_id)}"
        data = {"name": f"{self.new_champ[0]}, {self.role_or_aram}",
                "primaryStyleId": self.runes["primary_runes"][0],
                "subStyleId": self.runes["secondary_runes"][0],
                "selectedPerkIds": self.runes["primary_runes"][1:] +
                                   self.runes["secondary_runes"][1:] +
                                   self.runes["fragments"],
                "current": True,
                "isActive": True}

        r = requests.put(url, verify=False, auth=auth_header, json=data)

    @staticmethod
    def __get_page_id(base_url, auth_header):
        url = base_url + "/lol-perks/v1/currentpage"
        r = requests.get(url, verify=False, auth=auth_header)
        return r.json()

    def __prepare_driver(self, champ_name):
        if self.assigned_role:
            url = f"https://u.gg/lol/champions/{champ_name}/build?rank=diamond_2_plus&role={self.assigned_role}"
            self.role_or_aram = self.assigned_role
        else:
            url = f"https://u.gg/lol/champions/aram/{champ_name}-aram"
            self.role_or_aram = "Aram"

        driver.get(url)
        WebDriverWait(driver, 20).until(EC.visibility_of_element_located(
            (By.XPATH, "//*[@id='content']/div/div[1]/div/div/div[5]/div/div[2]/div[1]/div[2]/div[1]/div[1]/div")))

    def scrapeUGG(self, champ_name="neeko"):
        page = driver.page_source
        soup = bs(page, 'html.parser')

        primary_tree = soup.find_all("div", {"class": "rune-tree_v2 primary-tree"})[0]
        secondary_tree = soup.find_all("div", {"class": "secondary-tree"})[0]

        primary_runes = self.__get_primary_runes(primary_tree)
        secondary_runes = self.__get_secondary_runes(secondary_tree)
        fragments = self.__get_fragments(secondary_tree)

        self.runes = {"primary_runes": primary_runes,
                      "secondary_runes": secondary_runes,
                      "fragments": fragments}

    def __get_primary_runes(self, primary_tree):
        keystone = primary_tree.find_all("div", {"class": "perk keystone perk-active"})[0]
        sub_runes = primary_tree.find_all("div", {"class": "perk perk-active"})
        style = primary_tree.find_all("div", {"class": "perk-style-title"})[0].text.lower()
        runes = [RUNE_DICT['name_to_id'][style]]
        runes += [self.__get_rune_id(keystone, prefix="The Keystone")]
        runes += [self.__get_rune_id(sub_rune, prefix="The Rune") for sub_rune in sub_runes]
        return runes

    def __get_secondary_runes(self, secondary_tree):
        sub_runes = secondary_tree.find_all("div", {"class": "perk perk-active"})
        style = secondary_tree.find_all("div", {"class": "perk-style-title"})[0].text.lower()
        runes = [RUNE_DICT['name_to_id'][style]]
        runes += [self.__get_rune_id(sub_rune, prefix="The Rune") for sub_rune in sub_runes]
        return runes

    def __get_fragments(self, secondary_tree):
        fragments = secondary_tree.find_all("div", {"class": "shard shard-active"})
        fragments = [self.__get_rune_id(fragment, prefix="The", suffix="Shard") for fragment in fragments]
        return fragments

    @staticmethod
    def __get_rune_id(rune, prefix="", suffix=""):
        
        rune_name = rune.find("img")["alt"] \
            .replace(f"{prefix}", "") \
            .replace(" ", "") \
            .replace(f"{suffix}", "") \
            .replace(":", "") \
            .lower()

        if rune_name == "adaptiveforce":
            rune_name = "adaptive"
        elif rune_name == "magicresist":
            rune_name = "magicres"
        elif rune_name == "scalingcdr":
            rune_name = "cdrscaling"
        elif rune_name == "scalingbonushealth":
            rune_name = "healthscaling"

        rune_id = RUNE_DICT["name_to_id"][rune_name]
        return rune_id

    def __parse_response(self, response):
        self.player_pos = response[2]["data"]["localPlayerCellId"] % 5
        self.phase = response[2]["data"]["timer"]["phase"]
        self.champ_id = response[2]["data"]["myTeam"][self.player_pos]["championId"]
        self.assigned_role = response[2]["data"]["myTeam"][self.player_pos]["assignedPosition"]

        if self.phase == "FINALIZATION" or len(response[2]["data"]["actions"]) == 0:
            self.is_final_pick = True
        else:
            self.is_final_pick = response[2]["data"]["actions"][0][self.player_pos]["completed"]

    def __get_champ_name(self):
        url_champs = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champions/{self.champ_id}.json"
        r = requests.get(url_champs).json()
        return r["name"], r["alias"]

rc = runechanger()
with webdriver.Firefox(options=opts) as driver:
    asyncio.get_event_loop().run_until_complete(rc.listener())

from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.firefox.options import Options
from selenium import webdriver
from bs4 import BeautifulSoup as bs
import json
import os

import requests
from requests.auth import HTTPBasicAuth

from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


opts = Options()
opts.headless = True

with open("rune_data.json", "r") as f:
    RUNE_DICT = json.load(f)


class runechanger:
    def __init__(self):
        if os.name == 'nt':
            self.out = "C:\Riot Games\League of Legends/lockfile"
        else:
            self.out = "/Applications/League of Legends.app/Contents/LoL/lockfile"
        with open(self.out, 'r') as f:
            data = f.readline().strip().split(":")
        self.port = data[2]
        self.password = data[3]
        self.scheme = data[4]

        self.url = f"wss://riot:{self.password}@127.0.0.1:{str(self.port)}"
        self.base_url = f"{self.scheme}://127.0.0.1:{self.port}"
        self.auth_header = HTTPBasicAuth('riot', self.password)

        items_url = "https://ddragon.leagueoflegends.com/cdn/11.16.1/data/en_US/item.json"
        self.items_res = requests.get(items_url).json()

        self.phase = None
        self.champ_id = None
        self.assigned_role = None
        self.is_final_pick = None
        self.new_champ = (None, None)
        self.role_or_aram = None
        self.skill_order = None
        self.summoner_id = None
        self.items = []
        self.starting_items = []
        self.runes = {"primary_runes": None,
                      "secondary_runes": None,
                      "fragments": None}
        print("LoL RuneChanger started up successfully.")

    def listener(self):
        while True:
            # Client open, not in champselect
            page = requests.get(f"{self.base_url}/lol-champ-select/v1/session",
                                verify=False, auth=self.auth_header).json()
            if "errorCode" not in page:
                # Entered champselect
                self.__parse_response(page)
                if self.champ_id != 0:
                    # Champ chosen
                    champ_name = self.__get_champ_name()[1]
                    if self.new_champ != (champ_name, self.new_champ[1]):
                        self.new_champ = (champ_name, self.new_champ[1])
                        self.__prepare_driver(champ_name.lower())
                        new_champ_or_role = True

                    if self.phase == "FINALIZATION" and new_champ_or_role:
                        self.__scrapeUGG()
                        self.__set_runes()
                        self.__set_items()
                        self.__update_cli()
                        self.phase == None
                        new_champ_or_role = False

    def __item_names_to_ids(self):
        starting_item_ids = []
        for starting_item_lists in self.starting_items:
            x = []
            for sil in starting_item_lists:
                x += [item for item in self.items_res["data"]
                      if self.items_res["data"][item]["name"] == sil]
            starting_item_ids.append(x)

        core_item_ids = []
        for core_item_lists in self.core_items:
            x = []
            for sil in core_item_lists:
                x += [item for item in self.items_res["data"]
                      if self.items_res["data"][item]["name"] == sil]
            core_item_ids.append(x)

        item_ids = []
        for xitem in self.items:
            item_ids.append([item for item in self.items_res["data"]
                            if self.items_res["data"][item]["name"] == xitem][0])

        self.blocks = []
        for i, slist in enumerate(starting_item_ids):
            self.blocks.append({
                "type": f"Starting items {i+1}",
                        "hideIfSummonerSpell": "",
                        "showIfSummonerSpell": "",
                        "items": [{"id": list_item, "count": 1} for list_item in slist]
            })

        for i, slist in enumerate(core_item_ids):
            self.blocks.append({
                "type": f"Core items {i+1}",
                        "hideIfSummonerSpell": "",
                        "showIfSummonerSpell": "",
                        "items": [{"id": list_item, "count": 1} for list_item in slist]
            })

        self.blocks.append({
            "type": f"Popular items on {self.new_champ[0]} in popularity order",
                    "hideIfSummonerSpell": "",
                    "showIfSummonerSpell": "",
                    "items": [{"id": itemid, "count": 1} for itemid in item_ids]
        })

    def __set_items(self):
        self.__get_item_page_id()
        self.__item_names_to_ids()
        data = {
            "timestamp": 0,
            "accountId": self.summoner_id,
            "itemSets": [{
                "uid": str(self.uid),
                "title": f"{self.new_champ[0]} / {self.role_or_aram} / {' -> '.join(self.skill_order)}",
                "mode": "any",
                "map": "any",
                "type": "custom",
                "sortrank": 0,
                "startedFrom": "blank",
                "associatedChampions": [self.champ_id],
                "associatedMaps": [0, 11, 12],
                "blocks": self.blocks,
                "preferredItemSlots": [{
                        "id": "string",
                        "preferredItemSlot": 0}]}]}
        url = self.base_url + \
            f"/lol-item-sets/v1/item-sets/{self.summoner_id}/sets"
        r = requests.put(url, verify=False, auth=self.auth_header, json=data)

    def __set_runes(self):
        page_id = self.__get_rune_page_id()["id"]
        url = f"{self.base_url}/lol-perks/v1/pages/{str(page_id)}"
        data = {"name": f"{self.new_champ[0]} @ {self.role_or_aram}",
                "primaryStyleId": self.runes["primary_runes"][0],
                "subStyleId": self.runes["secondary_runes"][0],
                "selectedPerkIds": self.runes["primary_runes"][1:] +
                self.runes["secondary_runes"][1:] +
                self.runes["fragments"],
                "current": True,
                "isActive": True}

        r = requests.put(url, verify=False, auth=self.auth_header, json=data)

    def __get_rune_page_id(self):
        url = self.base_url + "/lol-perks/v1/currentpage"
        r = requests.get(url, verify=False, auth=self.auth_header)
        return r.json()

    def __get_item_page_id(self):
        url = self.base_url + \
            f"/lol-item-sets/v1/item-sets/{self.summoner_id}/sets"
        r = requests.get(url, verify=False, auth=self.auth_header)
        with open("test.json", 'w') as f:
            json.dump(r.json(), f, indent=4)
        self.uid = r.json()["itemSets"][0]["uid"]

    def __clean_role(self, role):
        if role.startswith("t"):
            self.assigned_role = "top"
        elif role.startswith("j"):
            self.assigned_role = "jungle"
        elif role.startswith("m"):
            self.assigned_role = "mid"
        elif role.startswith("b"):
            self.assigned_role = "bot"
        else:
            self.assigned_role = "support"

    @staticmethod
    def __clean_role_items(role):
        if role == "mid":
            role = "middle"
        elif role == "bot":
            role = "adc"
        return role

    def __prepare_driver(self, champ_name):
        if self.assigned_role:
            self.__clean_role(self.assigned_role.lower())
            role = self.__clean_role_items(self.assigned_role)
            url = f"https://u.gg/lol/champions/{champ_name}/build?rank=diamond_2_plus&role={self.assigned_role}"
            items_url = f"https://www.leagueofgraphs.com/champions/items/{champ_name}/{role}"

            self.role_or_aram = self.assigned_role
        else:
            url = f"https://u.gg/lol/champions/aram/{champ_name}-aram"
            items_url = f"https://www.leagueofgraphs.com/champions/items/{champ_name}/diamond/aram"
            self.role_or_aram = "Aram"

        driver.switch_to.window(driver.window_handles[0])
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.visibility_of_element_located(
            (By.XPATH, "//*[@id='content']/div/div[1]/div/div/div[5]/div/div[2]/div[1]/div[2]/div[1]/div[1]/div")))

        if "https://static.u.gg/assets/ugg/icons/alert-yellow.svg" in driver.page_source:
            url = f"https://u.gg/lol/champions/{champ_name}/build?role={self.assigned_role}"
            driver.get(url)
            WebDriverWait(driver, 20).until(EC.visibility_of_element_located(
                (By.XPATH, "//*[@id='content']/div/div[1]/div/div/div[5]/div/div[2]/div[1]/div[2]/div[1]/div[1]/div")))

        driver.switch_to.window(driver.window_handles[1])
        driver.get(items_url)
        WebDriverWait(driver, 20).until(EC.visibility_of_element_located(
            (By.XPATH, "//*[@id='topItemsTable']/tbody/tr[2]/td[1]/img")))

    def __scrape_items(self):

        self.items = []
        self.starting_items = []
        self.core_items = []

        driver.switch_to.window(driver.window_handles[1])
        soup = bs(driver.page_source, 'html.parser')
        table = soup.find_all("table", {"class": "data_table sortable_table"})
        trs = table[3].find_all("tr")
        for i, tr in enumerate(trs):
            if i == 0:
                continue
            elif i == 11:
                break
            self.items.append(tr.find("img")["alt"])

        trs = table[0].find_all("tr")
        for i, tr in enumerate(trs):
            if i == 0:
                continue
            elif i == 4:
                break
            self.core_items.append([x["alt"] for x in tr.find_all("img")])

        table = soup.find_all(
            "table", {"class": "data_table itemStarters sortable_table"})
        trs = table[0].find_all("tr")
        for i, tr in enumerate(trs):
            if i == 0:
                continue
            elif i == 4:
                break
            self.starting_items.append([x["alt"] for x in tr.find_all("img")])

    def __scrapeUGG(self):
        driver.switch_to.window(driver.window_handles[0])
        page = driver.page_source
        soup = bs(page, 'html.parser')
        primary_tree = soup.find_all(
            "div", {"class": "rune-tree_v2 primary-tree"})[0]
        secondary_tree = soup.find_all("div", {"class": "secondary-tree"})[0]
        skill_list = soup.find_all("div", {"class": "skill-priority-path"})[0]

        primary_runes = self.__get_primary_runes(primary_tree)
        secondary_runes = self.__get_secondary_runes(secondary_tree)
        fragments = self.__get_fragments(secondary_tree)
        self.__scrape_items()
        self.__get_skill_order(skill_list)

        self.runes = {"primary_runes": primary_runes,
                      "secondary_runes": secondary_runes,
                      "fragments": fragments}

    def __get_primary_runes(self, primary_tree):
        keystone = primary_tree.find_all(
            "div", {"class": "perk keystone perk-active"})[0]
        sub_runes = primary_tree.find_all("div", {"class": "perk perk-active"})
        style = primary_tree.find_all(
            "div", {"class": "perk-style-title"})[0].text.lower()
        runes = [RUNE_DICT['name_to_id'][style]]
        runes += [self.__get_rune_id(keystone, prefix="The Keystone")]
        runes += [self.__get_rune_id(sub_rune, prefix="The Rune")
                  for sub_rune in sub_runes]
        return runes

    def __get_secondary_runes(self, secondary_tree):
        sub_runes = secondary_tree.find_all(
            "div", {"class": "perk perk-active"})
        style = secondary_tree.find_all(
            "div", {"class": "perk-style-title"})[0].text.lower()
        runes = [RUNE_DICT['name_to_id'][style]]
        runes += [self.__get_rune_id(sub_rune, prefix="The Rune")
                  for sub_rune in sub_runes]
        return runes

    def __get_fragments(self, secondary_tree):
        fragments = secondary_tree.find_all(
            "div", {"class": "shard shard-active"})
        fragments = [self.__get_rune_id(
            fragment, prefix="The", suffix="Shard") for fragment in fragments]
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
        cellid = response["localPlayerCellId"] % 5
        self.phase = response["timer"]["phase"]
        self.champ_id = response["myTeam"][cellid]["championId"]
        self.assigned_role = response["myTeam"][cellid]["assignedPosition"]
        self.summoner_id = response["myTeam"][cellid]["summonerId"]

    def __get_champ_name(self):
        url_champs = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champions/{self.champ_id}.json"
        r = requests.get(url_champs).json()
        if r["alias"] == "MonkeyKing":
            r["alias"] = "wukong"
        return r["name"], r["alias"]

    def __get_skill_order(self, skill_list):
        skills = skill_list.find_all(
            "div", {"class": "skill-label bottom-center"})
        self.skill_order = [skill.text for skill in skills]

    def __update_cli(self):
        print("-------------------------------------------")
        print("Lol RuneChanger")
        print(f"Champ: {self.new_champ[0]}")
        print(f"Role: {self.role_or_aram}")
        print(f"levelup: {' -> '.join(self.skill_order)}")

        print(f"\nStarting items: \n")
        for i, item in enumerate(self.starting_items):
            print(f"\t{i + 1}. {', '.join(item)}")

        print(f"\nMost common items: \n")
        for i, item in enumerate(self.items):
            print(f"\t{i+1}. {item}")


rc = runechanger()
with webdriver.Firefox(options=opts) as driver:
    driver.execute_script("window.open('about:blank', 'tab2');")
    rc.listener()

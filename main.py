#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, time, json, math
import requests
from collections import defaultdict
from heapq import heappop, heappush

targetRepo = os.environ.get("TARGET_REPO", "fortheusers/switch-hbas-repo")

ignoreData = {}

def fetchIgnoreData():
    # Appstore hosts a cross-repo JSON of which version tags to ignore
    resp = requests.get("https://wiiubru.com/appstore/ignore.json")
    ignoreData.update(resp.json())

# calculates the Levenshtein distance between two words
# https://en.wikipedia.org/wiki/Levenshtein_distance
def editDistance(word1, word2):
    # https://leetcode.com/problems/edit-distance/submissions/1602141735
    # take the action that brings us closest to word2
    to_process = [(0, 0, word1)] # steps taken, current pos, current word
    seen = defaultdict(lambda: math.inf)
    while to_process:
        steps, pos, word = heappop(to_process)
        if seen[(pos, word)] <= steps:
            continue
        seen[(pos, word)] = steps
        if word == word2:
            # we're done!
            return steps
        # if this position is the same, just advance until they're different
        if pos < len(word2) and pos < len(word) and word[pos] == word2[pos]:
            heappush(to_process, (steps, pos+1, word))
            continue
        # try to just straight up replace our current position with the right value
        if pos < len(word2) and pos < len(word):
            heappush(to_process, (steps+1, pos+1, word[:pos] + word2[pos] + word[pos+1:]))
        # try deleting the current character
        if pos < len(word):
            heappush(to_process, (steps+1, pos, word[:pos] + word[pos+1:]))
        # try inserting the right character
        if pos < len(word2):
            heappush(to_process, (steps+1, pos+1, word[:pos] + word2[pos] + word[pos:]))
    return -1

def cloneRepo():
    if os.path.exists("metadata-repo"):
        os.system("rm -rf metadata-repo")
        print("Removed existing metadata-repo directory.")
    os.system(f"git clone https://github.com/{targetRepo}.git metadata-repo")

    # identify ourselves to git
    os.chdir("metadata-repo")
    os.system("git config user.name 'Dragonite'")
    os.system("git config user.email 'fight@fortheusers.org'")
    os.chdir("..")

def resetAndRefreshRepo():
    os.chdir("metadata-repo")
    os.system("git reset --hard HEAD")
    os.system("git checkout main")
    os.system("git pull")
    os.chdir("..")

def cleanVersion(version):
    # remove any leading 'v' or 'V' and trailing whitespace
    version = version.lstrip("vV").strip()
    # remove certain prefix/suffixes
    for word in ["switch"]:
        if version.lower().startswith(word):
            version = version[len(word):].strip()
        if version.lower().endswith(word):
            version = version[:-len(word)].strip()
    # any edge dashes
    return version.strip("-")

def stripMarkdown(text):
    # TODO: Remove certain markdown symbols, and the word changelog
    return text

def escapeNewlines(text):
    # HBAS expects newlines to be represented as "\\n"
    # which means we have to escape the slashes, thus "\\\\n"
    return text.replace("\n", "\\n").replace("\r", "")

def getGHInfo(url):
    if not url:
        return None, None
    # extract the GitHub repo and name from the URL
    if not url.startswith("https://github.com/"):
        return None, None
    parts = url.split("/")
    if len(parts) < 5:
        return None, None
    return parts[3], parts[4]

def checkForUpdates():
    # for each of our packages, check their Github repo
    # for releases, and if the version isn't ignored and
    # is different than our existing one, create a PR for it
    os.chdir("metadata-repo/packages")
    for package in os.listdir("."):
        print(f"Checking package: {package}")
        with open(f"{package}/pkgbuild.json", "r") as f:
            pkgbuild = json.loads(f.read())
            curVersion = cleanVersion(pkgbuild["info"].get("version", ""))
            ghRepo, ghName = getGHInfo(pkgbuild["info"].get("url", ""))
            if not ghRepo or not ghName:
                print(f"Package {package} does not have a valid GitHub URL.")
                continue
            # fetch the latest release data from GitHub
            releaseUrl = f"https://api.github.com/repos/{ghRepo}/{ghName}/releases/latest"
            headers = {
                "Authorization": f"token {os.environ.get('GH_TOKEN', '')}",
            }
            resp = requests.get(releaseUrl, headers=headers)
            if resp.status_code != 200:
                print(f"Failed to fetch latest release for {package}: {resp.status_code} {resp.text}")
                continue
            releaseData = resp.json()
            # check if the version is the same, or ignored
            tagName = cleanVersion(releaseData.get("tag_name", ""))
            if tagName == curVersion or ignoreData.get(package, "") == tagName:
                print(f"No update for {package}, current version is {curVersion}, latest is {tagName}.")
                continue
            print(f"New update found for {package}: {curVersion} -> {tagName}.")
            # create a PR for this package
            createPR(package, releaseData)

# this command assumes that we are in the metadata-repo already
def createPR(package, releaseData):
    changelog = stripMarkdown(releaseData.get("body", ""))
    version = cleanVersion(releaseData.get("tag_name", ""))

    if not version:
        print(f"Package {package} has no valid version in the release data.")
        return

    # check if the package exists first
    if not os.path.exists(f"{package}/pkgbuild.json"):
        print(f"pkgbuild for {package} does not exist in the metadata-repo")
        return
    
    os.system(f"git checkout -b {package}-{version}")

    # read existing pkgbuild data
    with open(f"{package}/pkgbuild.json", "r") as f:
        pkgbuild = json.loads(f.read())
        prevChangelog = pkgbuild.get("changelog", "")
        pkgbuild["info"]["version"] = version
        pkgbuild["changelog"] = f"v{version}\\n" + escapeNewlines(changelog) + ("\\n\\n" + prevChangelog if prevChangelog else "")

        # go through each asset, and for each download URL,
        # compare it to one of the release assets, and take
        # the one with the closest levenstein distance
        for curAsset in pkgbuild.get("assets", []):
            # only process github asset URLs
            if not curAsset.get("url", "").startswith("https://github.com/"):
                continue
            # also skip any icon/banner/screenshot types
            if curAsset.get("type", "") in ["icon", "banner", "screenshot"]:
                continue
            # take closest LV distance
            closestUrl = None
            closestDistance = math.inf
            for assetData in releaseData.get("assets", []):
                if "browser_download_url" not in assetData:
                    continue
                distance = editDistance(curAsset["url"], assetData["browser_download_url"])
                if distance >= 0:
                    if distance < closestDistance:
                        closestDistance = distance
                        closestUrl = assetData["browser_download_url"]
            if closestUrl:
                curAsset["url"] = closestUrl

    # overwrite the new data and commit it
    with open(f"{package}/pkgbuild.json", "w") as f:
        f.write(json.dumps(pkgbuild, indent=4, ensure_ascii=False))
    
    os.system("git add .")
    os.system(f"git commit -m '[auto] Update {package} to {version}'")

    # push our actual branch
    # os.system("git push origin HEAD")

fetchIgnoreData()
cloneRepo() # every start, clone the repo new

while True:
    resetAndRefreshRepo()
    checkForUpdates()
    time.sleep(60 * 60 * 2) # every 2 hours
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Mail: tongdongdong@outlook.com
import copy
import random
import time
import os
import requests
from dns.qCloud import QcloudApiv3  # QcloudApiv3 DNSPod 的 API 更新了...
from dns.aliyun import AliApi
from dns.huawei import HuaWeiApi
import traceback
import json


def log_error(msg: str):
    print(f'[Error] [{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}] {msg}')


def log_info(msg: str):
    print(f'[INFO] [{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}] {msg}')


# 可以从https://shop.hostmonit.com获取
try:
    KEY = os.environ["KEY"]
except KeyError:
    KEY = "o1zrmHAF"
# CM:移动 CU:联通 CT:电信 AB:境外 DEF:默认
# 修改需要更改的 DNSPod 域名和子域名
# {"hostmonit.com": {"@": ["CM","CU","CT"], "shop": ["CM", "CU", "CT"], "stock": ["CM","CU","CT"]}}
DOMAINS = json.loads(os.environ["DOMAINS"])
# 腾讯云后台获取 https://console.cloud.tencent.com/cam/capi
SECRETID = os.environ["SECRETID"]  # 'AKIDV**********Hfo8CzfjgN'
SECRETKEY = os.environ["SECRETKEY"]  # 'ZrVs*************gqjOp1zVl'
# 默认为普通版本 不用修改
AFFECT_NUM = 2
# DNS服务商 如果使用DNSPod改为1 如果使用阿里云解析改成2  如果使用华为云解析改成3
DNS_SERVER = 1
# 如果试用华为云解析 需要从API凭证-项目列表中获取
REGION_HW = 'cn-east-3'
# 如果使用阿里云解析 REGION出现错误再修改 默认不需要修改 https://help.aliyun.com/document_detail/198326.html
REGION_ALI = 'cn-hongkong'
# 解析生效时间，默认为600秒 如果不是DNS付费版用户 不要修改!!!
TTL = 600
# A为筛选出IPv4的IP  AAAA为筛选出IPv6的IP
RECORD_TYPE = "A"


def get_optimization_ip():
    try:
        response = requests.post('https://api.hostmonit.com/get_optimization_ip',
                                 json={"key": KEY, "type": "v4" if RECORD_TYPE == "A" else "v6"},
                                 headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            resp_json = response.json()
            if resp_json["code"] == 200:
                return resp_json
            else:
                log_error(f'获取 Cloudflare IP 失败 Code: {resp_json["code"]} {resp_json["info"]}')
        else:
            log_error(f'获取 Cloudflare IP 失败 {response.status_code}')
    except Exception as e:
        traceback.print_exc()
        log_error(f"获取 Cloudflare IP 失败 {str(e)}")


def change_dns(line, s_info, c_info, domain, sub_domain, cloud):
    global AFFECT_NUM, RECORD_TYPE

    lines = {"CM": "移动", "CU": "联通", "CT": "电信", "AB": "境外", "DEF": "默认"}
    line = lines[line]

    try:
        create_num = AFFECT_NUM - len(s_info)
        if create_num > 0:
            for i in range(create_num):
                if len(c_info) == 0:
                    break
                c_item = c_info.pop(0)
                cf_ip = c_item["ip"]
                cloud.create_record(domain, sub_domain, cf_ip, RECORD_TYPE, line, TTL)
                log_info(f'CREATE DNS SUCCESS - DOMAIN: {domain} SUBDOMAIN: {sub_domain} RECORD_LINE: {line} '
                         f'RECORD_TYPE: {RECORD_TYPE} VALUE: {cf_ip} UP_TIME: {c_item["time"]}')
        else:
            s_ip_list = []
            for info in s_info:
                s_ip_list.append(info['value'])

            c_ip_list = []
            for info in c_info:
                c_ip_list.append(info['ip'])

            while len(s_info) > 0:
                if len(c_info) == 0:
                    break
                info = s_info.pop(0)
                if info['value'] in c_ip_list:
                    continue
                c_item = c_info.pop(0)
                cf_ip = c_item["ip"]
                if cf_ip in s_ip_list:
                    s_info.insert(0, info)
                    continue

                cloud.change_record(domain, info["recordId"], sub_domain, cf_ip, RECORD_TYPE, line, TTL)

                log_info(f'CHANGE DNS SUCCESS - DOMAIN: {domain} SUBDOMAIN: {sub_domain} RECORD_LINE: {line} '
                         f'RECORD_TYPE: {RECORD_TYPE} VALUE: {cf_ip} UP_TIME: {c_item["time"]}')

    except Exception as e:
        traceback.print_exc()
        log_error(f'CHANGE DNS ERROR - MESSAGE: {str(e)}')


def main(cloud):
    global AFFECT_NUM, RECORD_TYPE
    if len(DOMAINS) > 0:
        try:
            cf_ips = get_optimization_ip()
            if cf_ips is None or cf_ips["code"] != 200:
                log_error(f'GET CLOUDFLARE IP ERROR')
                return
            if isinstance(cf_ips["info"], list):
                cf_cm_ips = []
                cf_cu_ips = []
                cf_ct_ips = []
                for tmp_ip in cf_ips["info"]:
                    if tmp_ip["line"] == "CM":
                        cf_cm_ips.append(tmp_ip)
                    elif tmp_ip["line"] == "CU":
                        cf_cu_ips.append(tmp_ip)
                    elif tmp_ip["line"] == "CT":
                        cf_ct_ips.append(tmp_ip)
            else:
                cf_cm_ips = cf_ips["info"]["CM"]
                cf_cu_ips = cf_ips["info"]["CU"]
                cf_ct_ips = cf_ips["info"]["CT"]

            for domain, sub_domains in DOMAINS.items():
                for sub_domain, lines in sub_domains.items():

                    cf_ips_map = {
                        "CM": cf_cm_ips.copy(),
                        "CU": cf_cu_ips.copy(),
                        "CT": cf_ct_ips.copy(),
                        "AB": cf_ct_ips.copy(),
                        "DEF": cf_ct_ips.copy()
                    }

                    ret = cloud.get_record(domain, 100, sub_domain, RECORD_TYPE)
                    if DNS_SERVER == 1 and "DP_Free" in ret["data"]["domain"]["grade"] and AFFECT_NUM > 2:
                        AFFECT_NUM = 2
                    s_info = {'CM': [], 'CU': [], 'CT': [], 'AB': [], 'DEF': []}
                    line_map = {"移动": "CM", "联通": "CU", "电信": "CT", "境外": "AB", "默认": "DEF"}
                    for record in ret["data"]["records"]:
                        s_line_type = line_map[record["line"]]
                        info = {"recordId": record["id"], "value": record["value"]}
                        s_info[s_line_type].append(info)

                    for line in lines:
                        if line in cf_ips_map:
                            change_dns(line, s_info[line], cf_ips_map[line], domain, sub_domain, cloud)
        except Exception as e:
            traceback.print_exc()
            log_error(f'CHANGE DNS ERROR - MESSAGE: {str(e)}')


if __name__ == '__main__':
    if DNS_SERVER == 1:
        cloud = QcloudApiv3(SECRETID, SECRETKEY)
    elif DNS_SERVER == 2:
        cloud = AliApi(SECRETID, SECRETKEY, REGION_ALI)
    elif DNS_SERVER == 3:
        cloud = HuaWeiApi(SECRETID, SECRETKEY, REGION_HW)
    RECORD_TYPE = "A"
    main(cloud)
    RECORD_TYPE = "AAAA"
    main(cloud)

import json
import os
import re
import time

import requests


class FreeNom(object):
    """
    FreeNom api请求
    """
    # 登录
    LOGIN_URL = 'https://my.freenom.com/dologin.php'
    # 查看域名状态
    DOMAIN_STATUS_URL = 'https://my.freenom.com/domains.php?a=renewals'
    # 域名续期
    RENEW_DOMAIN_URL = 'https://my.freenom.com/domains.php?submitrenewals=true'

    TOKEN_REGEX = 'name="token"\svalue="(?P<token>[a-zA-Z0-9]+)"'
    DOMAIN_INFO_REGEX = '<tr><td>(?P<domain>[^<]+)<\/td><td>[^<]+<\/td><td>[^<]+<span class="[^"]+">(?P<days>\d+)[' \
                        '^&]+&domain=(?P<id>\d+)"'
    LOGIN_STATUS_REGEX = '<li.*?Logout.*?<\/li>'

    def __init__(self, setting: dict):
        self.headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        self.session = requests.session()
        self.token_pattern = re.compile(self.TOKEN_REGEX)
        self.domain_info_pattern = re.compile(self.DOMAIN_INFO_REGEX)
        self.login_pattern = re.compile(self.LOGIN_STATUS_REGEX)
        self.setting = setting
        self.proxy = None
        self.find_proxy()

    def log(self, msg):
        print(str(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())) + " " + msg)

    def find_proxy(self):
        with self.session.get(self.setting.get('proxy_url')) as response:
            response_text = response.text
        proxy_list = response_text.splitlines()
        self.log('find proxy start')
        for proxy_item in proxy_list:
            check_proxy = {'http': 'socks5://' + proxy_item, 'https': 'socks5://' + proxy_item}
            try:
                with self.session.get('https://my.freenom.com/', timeout=10, proxies=check_proxy) as response:
                    if response.status_code == 200:
                        self.proxy = check_proxy
                        self.log('use proxy socks5://' + proxy_item)
                        break
            except:
                pass
        self.log('find proxy end')

    def request(self, method, url, data=None, headers=None) -> requests.Response:
        return self.session.request(method, url, data=data, headers=headers, proxies=self.proxy)

    def run(self) -> list:
        if self.proxy is None:
            self.log('proxy is None')
            return []

        self.login()
        html = self.get_domains()
        token_match = self.token_pattern.findall(html)
        domain_info_match = self.domain_info_pattern.findall(html)
        login_match = self.login_pattern.findall(html)

        if not login_match:
            self.log("FreeNom login parse failed")
            raise Exception("登录检查失败")

        if not token_match:
            self.log("FreeNom token parse failed")
            raise Exception("页面token检查失败")

        if not domain_info_match:
            self.log("FreeNom domain info parse failed")
            raise Exception("页面没有获取到域名信息")

        token = token_match[0]
        # print(f"waiting for renew domain info is {domain_info_match}")

        result = []

        for info in domain_info_match:
            time.sleep(1)
            domain, days, domain_id = info
            msg = "续期失败"

            if int(days) > 14:
                self.log(f"FreeNom domain *** can not renew, days until expiry is {days}")
                msg = "无需续期"
            else:
                response = self.renew_domain(token, domain_id)
                if response.find("Order Confirmation") != -1:
                    msg = "续期成功"
                    self.log(f"FreeNom renew domain *** is success")
                else:
                    self.log(f"FreeNom renew domain *** is fail")
            result.append({"domain": domain, "days": days, "msg": msg})
        if os.environ["NOTITY_TYPE"] == 'http':
            notify_config = json.loads(os.environ["NOTITY_CONFIG"])
            msg = ""
            for item in result:
                msg = msg + item['domain'] + ' 还有' + item['days'] + '天到期，' + item['msg'] + '\n'
            data = {'token': notify_config.get('token'), 'event': 'notify', 'content': msg}
            self.session.post(notify_config.get('url'), json=data)
        return result

    def login(self) -> bool:
        data = {
            'username': self.setting.get('username'),
            'password': self.setting.get('password'),
        }
        headers = {
            **self.headers,
            'Referer': 'https://my.freenom.com/clientarea.php'
        }
        with self.request('POST', self.LOGIN_URL, data=data, headers=headers) as response:
            if response.status_code == 200:
                return True
            else:
                self.log("FreeNom login failed")
                raise Exception("调用登录接口失败")

    def get_domains(self) -> str:
        headers = {
            'Referer': 'https://my.freenom.com/clientarea.php'
        }
        with self.request('GET', self.DOMAIN_STATUS_URL, headers=headers) as response:
            if response.status_code == 200:
                return response.text
            else:
                self.log("FreeNom check domain status failed")
                raise Exception("调用获取域名信息接口失败")

    def renew_domain(self, token, renewalid) -> str:
        headers = {
            **self.headers,
            "Referer": "https://my.freenom.com/domains.php?a=renewdomain&domain=" + str(renewalid)
        }
        data = {
            "token": token,
            "renewalid": renewalid,
            f"renewalperiod[{renewalid}]": "12M",
            'paymentmethod': 'credit'
        }

        with self.request('POST', self.RENEW_DOMAIN_URL, data=data, headers=headers) as response:
            if response.status_code == 200:
                return response.text
            else:
                self.log("FreeNom renew domain failed")
                raise Exception("调用续期接口失败接口失败")

    def __del__(self):
        self.session.close()


if __name__ == "__main__":
    results = FreeNom({
        'username': os.environ["USERNAME"],
        'password': os.environ["PASSWORD"],
        'proxy_url': os.environ["PROXY_URL"]
    }).run()

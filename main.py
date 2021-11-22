from os import environ
from random import randint
from time import sleep

import cv2
import httpx
import numpy as np
import urllib3
from loguru import logger

from captcha import guess

import smtplib
from email.mime.text import MIMEText
from email.header import Header

# 默认配置
defaults = {
    # 'student_id': '<你的学号>',
    # 'password': '<个人门户登录密码>',
    'random': False,
    'address': ['湖南省', '长沙市', '岳麓区', '湖南大学'],

    'max_trial': 20,
    'failed_wait': 60,
    'success_tint': ['今天已提交过打卡信息！', '成功']
}

# 默认请求头
headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/85.0.4183.102 Mobile Safari/537.36',
}

# 禁用不安全证书的警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Checker(httpx.Client):
    def __init__(self, configs):
        super().__init__(verify=False)
        self.configs = configs
        self.headers = headers
        
        
    def mailSend(self):

        content = '打卡成功'
        message = MIMEText(content, 'plain', 'utf-8')

        message['From'] = Header("王康", 'utf-8')  
        message['To'] =  Header("riptide", 'utf-8')
        
        subject = '疫情打卡提示'  #发送的主题，可自由填写
        message['Subject'] = Header(subject, 'utf-8') 
        try:
            smtpObj = smtplib.SMTP_SSL(self.configs['mail_host'], 465) 
            smtpObj.login(self.configs['sender'],self.configs['mail_pass'])  
            smtpObj.sendmail(self.configs['sender'], self.configs['receiver'], message.as_string())
            smtpObj.quit()
            print('邮件发送成功')
            
        except smtplib.SMTPException as e:
            print('邮件发送失败')
        

    def checkin(self):
        logger.info('尝试打卡中...')
        for trial in range(self.configs['max_trial']):
            try:
                logger.info('正在登录...')
                token = self.get('https://fangkong.hnu.edu.cn/api/v1/account/getimgvcode').json()['data']['Token']
                image_raw = self.get(f'https://fangkong.hnu.edu.cn/imagevcode?token={token}').content
                image = cv2.imdecode(np.frombuffer(image_raw, np.uint8), cv2.IMREAD_COLOR)
                code = guess(image)

                login = self.post(
                    'https://fangkong.hnu.edu.cn/api/v1/account/login',
                    data={
                        'Code': self.configs['student_id'],
                        'Password': self.configs['password'],
                        'WechatUserinfoCode': None,
                        'VerCode': code,
                        'Token': token
                    }
                ).json()
                if login['code']:  # code 不为 0 则代表登录失败
                    logger.error(login)
                    continue

                if self.configs['random']:
                    interval = (3, 8)
                else:
                    interval = (5, 5)
                message = self.post(
                    'https://fangkong.hnu.edu.cn/api/v1/clockinlog/add',
                    headers={
                        **self.headers,
                        **{
                            'Cache-Control': 'no-cache',
                            'Host': 'fangkong.hnu.edu.cn',
                            'Origin': 'https://fangkong.hnu.edu.cn',
                            'Pragma': 'no-cache',
                            'Referer': 'https://fangkong.hnu.edu.cn/app/',
                            'Sec-Fetch-Dest': 'empty',
                            'Sec-Fetch-Mode': 'cors',
                            'Sec-Fetch-Site': 'same-origin'
                        }
                    },
                    json={
                        'Longitude': None,
                        'Latitude': None,
                        'RealProvince': self.configs['address'][0],
                        'RealCity': self.configs['address'][1],
                        'RealCounty': self.configs['address'][2],
                        'RealAddress': self.configs['address'][3],
                        'BackState': 1,
                        'MorningTemp': f'36.{randint(*interval)}',
                        'NightTemp': f'36.{randint(*interval)}',
                        'tripinfolist': []
                    }
                ).json()['msg']
                if message in self.configs['success_tint']:
                    logger.info(f'服务器消息：{message}')
                    logger.info('自动打卡成功！')
                    self.mailSend()
                    
                    break
                else:
                    raise RuntimeError(f'打卡失败：{message}')
            except Exception as err:
                logger.error(err)
                logger.info(f'已失败 {trial + 1} 次，将于 {self.configs["failed_wait"]} 秒后重试')
                sleep(self.configs['failed_wait'])
        else:
            raise RuntimeError('重试次数过多！')


def main():
    configs = {
        **defaults,
        **json.loads(environ['USER'] if 'USER' in environ else '{}')
    }
    # 检查是否配置正确
    assert 'student_id' in configs and 'password' in configs
    checker = Checker(configs)
    checker.checkin()


if __name__ == '__main__':
    main()

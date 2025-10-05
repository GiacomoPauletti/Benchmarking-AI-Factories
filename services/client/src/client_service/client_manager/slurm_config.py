from pydantic import BaseModel

# Default values
DEFAULT_URL = "http://slurmrestd.meluxina.lxp.lu:682"
DEFAULT_JWT = ""
DEFAULT_USER_NAME = ""
DEFAULT_API_VER   = "v0.0.40"
DEFAULT_ACCOUNT   = ""

class SlurmConfig(BaseModel):
    url         : str
    jwt         : str
    api_ver     : str
    user_name   : str
    account     :str

    def __init__(self, url: str, jwt: str, user_name: str, api_ver: str, account: str):
        self.url = url
        self.jwt = jwt
        self.user_name = user_name
        self.api_ver = api_ver
        self.account = account
        
    @staticmethod
    def tmp_load_default():
        return SlurmConfig(DEFAULT_URL, DEFAULT_JWT, 
                           DEFAULT_USER_NAME, DEFAULT_API_VER, 
                           DEFAULT_ACCOUNT)
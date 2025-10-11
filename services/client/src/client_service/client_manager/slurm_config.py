from pydantic import BaseModel

# Default values
DEFAULT_URL = "http://slurmrestd.meluxina.lxp.lu:6820"
DEFAULT_JWT = ""
DEFAULT_USER_NAME = ""
DEFAULT_API_VER   = "v0.0.40"
DEFAULT_ACCOUNT   = ""

class SlurmConfig(BaseModel):
    url: str = DEFAULT_URL
    jwt: str = DEFAULT_JWT
    api_ver: str = DEFAULT_API_VER
    user_name: str = DEFAULT_USER_NAME
    account: str = DEFAULT_ACCOUNT

    @classmethod
    def load_from_file(cls, file_path: str):
        with open(file_path, 'r') as file:
            lines = file.readlines()
            config_dict = {}
            for line in lines:
                key, value = line.strip().split('=')
                config_dict[key] = value

            result = cls()
            result.url = config_dict.get('url', DEFAULT_URL)
            result.jwt = config_dict.get('jwt', DEFAULT_JWT)
            result.user_name = config_dict.get('user_name', DEFAULT_USER_NAME)
            result.api_ver = config_dict.get('api_ver', DEFAULT_API_VER)
            result.account = config_dict.get('account', DEFAULT_ACCOUNT)
            
            return result
        


    @staticmethod
    def tmp_load_default():
        return SlurmConfig()
    
    def __str__(self):
        return f"SlurmConfig(url={self.url}\n, jwt={'***' if self.jwt else ''}\n, api_ver={self.api_ver}\n, user_name={self.user_name}\n, account={self.account})"
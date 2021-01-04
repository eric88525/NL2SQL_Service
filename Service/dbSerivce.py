import mysql.connector
import json
class DBService():
    def __init__(self,config):    
        self.config = config
        self.type_map = {
            'varchar':'text',
            'float':'real'
        }


    # get maxdb & cursor
    def get_connect(self):
        maxdb = mysql.connector.connect(
            host = self.config["host"],
            user = self.config["user"],
            password = self.config["password"],
            database = self.config["database"],
        )
        cursor=maxdb.cursor()
        return maxdb,cursor

    # 拿到單個table內容物 [(col1,col2,col3),(),()...]
    def get_table(self,table_name):
        try:
            maxdb,cursor = self.get_connect()
            sql = f"SELECT * FROM {table_name}"
            cursor.execute(sql)
            result = cursor.fetchall()
            self.close_conn(maxdb,cursor)
            return result
        except:
            return []

     # 拿到table 列表   回傳 ['name1','name2' ...]
    def get_table_list(self):
        maxdb,cursor = self.get_connect()
        sql = f"SELECT * FROM {self.config['table_map']}"
        #sql = "SELECT * FROM INFORMATION_SCHEMA.TABLES;"
        cursor.execute(sql)
        result = cursor.fetchall()
        result = [i[0] for i in result]
        print(result)
        return result


    # 拿到表頭資訊 回傳 [(name,name...),(type,type...)]
    def get_headers(self,table_name):
        try:
            maxdb,cursor = self.get_connect()
            sql = f'SELECT COLUMN_NAME,DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=\'{table_name}\''
            cursor.execute(sql)
            result = cursor.fetchall()
            result = [ [ i[0] for i in result] ,[ i[1] for i in result] ]
            self.close_conn(maxdb,cursor)
            return result
        except:
            return []

    # close maxdb & cursor
    def close_conn(self,maxdb,cursor):
        maxdb.close()
        cursor.close()

    # get table column list like: [v1,v2,v3...]
    def get_columns(self,table_name,col_name):
        maxdb,cursor = self.get_connect()
        sql = f'SELECT `{col_name}` FROM {table_name}'
        cursor.execute(sql)
        result = cursor.fetchall()
        result = [i[0] for i in result]
        self.close_conn(maxdb,cursor)
        return result

    # run sql command
    def exe_sql(self,sql):
        maxdb,cursor = self.get_connect()
        sql = str(sql)
        cursor.execute(sql)
        result = cursor.fetchall()
        self.close_conn(maxdb,cursor)
        return result
        
          

if __name__ == '__main__':
    config = {
        'host' : '127.0.0.1',
        'user' : "ericzone",
        'password': "ericzone",
        'database' : "nl2sql",
    }

    service = DBService(config)
    ss = "SELECT (`办公电话`) ,(`邮箱`) FROM `Table_43b06b7d1d7111e989d6f40f24344a08` WHERE `姓名` = \"杨涛\" "
    print(service.exe_sql( ss) )
    #print(service.get_columns('Table_43ad6bdc1d7111e988a6f40f24344a08','平均溢价率(%)'))
    #print(service.get_headers('Table_43ad6bdc1d7111e988a6f40f24344a08'))
    #print(service.get_table('table_5a4a8bcc312b11e9a932542696d6e445'))
    #print(service.get_table_list('namemap'))

    
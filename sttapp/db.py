from peewee import *

# from playhouse.sqliteq import SqliteQueueDatabase
from flask_login import UserMixin

# import re

from instance.config import *

# database = SqliteQueueDatabase("./instance/db.db")
database = MySQLDatabase(
    MYSQL_DB,
    user=MYSQL_USER,
    password=MYSQL_PASS,
    host=MYSQL_HOST,
    port=MYSQL_PORT,
)

# For SQLite, adds regex support IIRC
# @database.func()
# def regexp(expr, s):
#     # print("raw string " + s)
#     s = re.sub("{[0-9]*}", "", s)
#     # print("replaced string " + s)
#     result = re.search(expr, s, flags=re.IGNORECASE)
#     return result is not None


class LongTextField(TextField):
    field_type = "LONGTEXT"


class BaseModel(Model):
    class Meta:
        database = database


class Inventory(Model):
    def refresh(self):
        return type(self).get(self._pk_expr())

    total_paths = IntegerField()
    skipped_paths = IntegerField()
    finished_paths = IntegerField()
    start_date = DateTimeField()
    end_date = DateTimeField(null=True)
    error = TextField(null=True)

    class Meta:
        database = database


class Call(Model):
    path = CharField(unique=True)
    incoming = BooleanField()
    initiating = IntegerField()
    receiving = IntegerField()
    text = LongTextField()
    date_time = DateTimeField()
    duration = FloatField()
    inventory = ForeignKeyField(Inventory, backref="calls")

    class Meta:
        database = database


class TimeStamp(Model):
    position = IntegerField()
    timestamp = IntegerField()
    call = ForeignKeyField(Call, backref="timestamps")
    
    class Meta:
        database = database


class User(Model, UserMixin):
    username = CharField()
    password = CharField()

    class Meta:
        database = database

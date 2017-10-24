#!/usr/bin/env python3
"""Export the data needed for auth in JSON format, from Plat/al database

Requires:
    pip install PyMySQL
    platal.conf file
"""
import configparser
import pymysql
import json
import sys

# Load platal.conf and connect
conf = configparser.SafeConfigParser()
conf.read('platal.conf')
db = pymysql.connect(
    host=conf['Core']['dbhost'].strip('"'),
    user=conf['Core']['dbuser'].strip('"'),
    password=conf['Core']['dbpwd'].strip('"'),
    db=conf['Core']['dbdb'].strip('"'),
    charset='utf8mb4',
)

result = {
    'authgroupex': [],
    'accounts': [],
}


def get_cols_from_query(query):
    select_part = query.split(' FROM', 1)[0].split('SELECT', 1)[1]
    return [p.split()[-1].split('.')[-1] for p in select_part.split(',')]


# Export authgroupex info
with db.cursor() as cursor:
    print("Exporting group_auth table")
    sql = """
        SELECT  ga.privkey, ga.name, ga.datafields, ga.returnurls, ga.flags,
                g.diminutif AS groupid, g.nom AS groupname
          FROM  group_auth AS ga
     LEFT JOIN  groups AS g ON (g.id = ga.group_id)
    """
    cols = get_cols_from_query(sql)
    cursor.execute(sql)
    for row in cursor:
        entry = dict(zip(cols, row))
        result['authgroupex'].append(entry)

# Export accounts info
accounts = {}
with db.cursor() as cursor:
    print("Exporting accounts table")
    sql = """
        SELECT  a.uid, a.hruid, a.password, a.type, a.is_admin,
                a.firstname, a.lastname, a.full_name, a.directory_name, a.display_name,
                a.sex, a.email
          FROM  accounts AS a
         WHERE  a.state = 'active'
     """
    cols = get_cols_from_query(sql)
    cursor.execute(sql)
    for row in cursor:
        entry = dict(zip(cols, row))
        uid = int(entry['uid'])
        # Remove uid from exported data, but use it in order to gather more data
        del entry['uid']
        entry['email_source'] = {}
        entry['email_redirect'] = {}
        entry['groups'] = {}
        accounts[uid] = entry

with db.cursor() as cursor:
    print("Exporting email_source_account table")
    sql = """
        SELECT  s.uid, s.type, CONCAT(s.email, '@', d.name) AS email, s.flags
          FROM  email_source_account  AS s
    INNER JOIN  email_virtual_domains AS m ON (s.domain = m.id)
    INNER JOIN  email_virtual_domains AS d ON (d.aliasing = m.id)
      ORDER BY  s.uid, d.id
    """
    cursor.execute(sql)
    for uid, stype, email, flags in cursor:
        uid = int(uid)
        if uid not in accounts:
            # Skip disabled accounts
            continue
        assert email not in accounts[uid]['email_source']
        accounts[uid]['email_source'][email] = stype
        if 'bestalias' in flags and accounts[uid]['email'] is None:
            accounts[uid]['email'] = email

with db.cursor() as cursor:
    print("Exporting email_redirect_account table")
    sql = """
        SELECT  r.uid, r.type, r.redirect
          FROM  email_redirect_account AS r
         WHERE  r.type != 'homonym'
    """
    cursor.execute(sql)
    for uid, rtype, email in cursor:
        uid = int(uid)
        if uid not in accounts:
            continue
        assert email not in accounts[uid]['email_redirect']
        accounts[uid]['email_redirect'][email] = rtype

with db.cursor() as cursor:
    print("Exporting group_members table")
    sql = """
        SELECT  gm.uid, g.diminutif AS groupid, gm.perms
          FROM  group_members AS gm
    INNER JOIN  groups AS g ON (g.id = gm.asso_id)
    """
    cursor.execute(sql)
    for uid, groupid, perms in cursor:
        uid = int(uid)
        if uid not in accounts:
            continue
        # Use English
        if perms == 'membre':
            perms = 'member'
        assert groupid not in accounts[uid]['groups']
        accounts[uid]['groups'][groupid] = perms

result['accounts'] = list(accounts.values())

# Output JSON
print("Writing JSON file")
with open('exported_for_auth.json', 'w') as f:
    json.dump(result, f, indent=2)
import pg8000


def connect(host, port, database, user, password):
    return pg8000.connect(
        user=user,
        host=host,
        database=database,
        port=int(port),
        password=password,
        timeout=10,
        application_name="ca_invoice_printer",
    )


def close(connection):
    if connection is not None:
        connection.close()


def fetch_invoices(connection, search_term="", limit=500):
    capped_limit = max(1, min(int(limit), 2000))
    term = (search_term or "").strip()
    pattern = "%" + term + "%"
    query = """
        SELECT
            at.transid,
            COALESCE(at.referencenumber, '') AS referencenumber,
            at.transdate,
            at.transtotal,
            COALESCE(at.transstatus, '') AS transstatus,
            COALESCE(
                NULLIF(o.orgname, ''),
                TRIM(COALESCE(o.firstname, '') || ' ' || COALESCE(o.lastname, '')),
                ''
            ) AS customer_name
        FROM public.acct_trans at
        LEFT JOIN public.org o ON at.orgid = o.org_id
        WHERE at.transtypecode = 'INVOICE'
          AND (
                %s = ''
                OR at.referencenumber ILIKE %s
                OR COALESCE(o.orgname, '') ILIKE %s
                OR COALESCE(o.firstname, '') ILIKE %s
                OR COALESCE(o.lastname, '') ILIKE %s
          )
        ORDER BY at.transdate DESC NULLS LAST, at.transid DESC
        LIMIT %s
    """
    cursor = connection.cursor()
    try:
        cursor.execute(query, (term, pattern, pattern, pattern, pattern, capped_limit))
        rows = cursor.fetchall()
    finally:
        cursor.close()

    invoices = []
    for row in rows:
        invoices.append(
            {
                "transid": row[0],
                "doc_number": row[1],
                "transdate": row[2],
                "total": row[3],
                "status": row[4],
                "customer": row[5],
            }
        )
    return invoices

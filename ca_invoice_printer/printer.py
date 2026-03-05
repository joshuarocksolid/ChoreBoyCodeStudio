from jasper_bridge import Report


def build_jdbc_url(host, port, database):
    return "jdbc:postgresql://{}:{}/{}".format(host, int(port), database)


def _fill_report(jrxml_path, host, port, database, user, password, trans_id):
    report = Report(jrxml_path)
    report.compile()
    report.fill(
        jdbc=build_jdbc_url(host, port, database),
        user=user,
        password=password,
        params={
            "?TransID": int(trans_id),
            "?CompNameAddr": "",
        },
    )
    return report


def preview_invoice(jrxml_path, host, port, database, user, password, trans_id):
    report = _fill_report(jrxml_path, host, port, database, user, password, trans_id)
    report.preview(title="Invoice Preview")


def print_invoice(jrxml_path, host, port, database, user, password, trans_id):
    report = _fill_report(jrxml_path, host, port, database, user, password, trans_id)
    return report.print(title="Print Invoice")

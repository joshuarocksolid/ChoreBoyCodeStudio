from jasper_bridge import Report


def build_jdbc_url(host, port, database):
    return "jdbc:postgresql://{}:{}/{}".format(host, int(port), database)


def build_and_fill_invoice_report(
    jrxml_path,
    host,
    port,
    database,
    user,
    password,
    trans_id,
    company_name_addr="",
):
    report = Report(jrxml_path)
    report.compile()
    report.fill(
        jdbc=build_jdbc_url(host, port, database),
        user=user,
        password=password,
        params={
            "?TransID": int(trans_id),
            "?CompNameAddr": company_name_addr,
        },
    )
    return report


def export_report(
    report,
    export_format,
    output_path=None,
    output_dir=None,
    zoom=2.0,
    text_page_width=120,
    text_page_height=60,
):
    fmt = str(export_format or "").strip().lower()
    if fmt == "pdf":
        return report.export_pdf(output_path)
    if fmt == "png":
        return report.export_png(output_dir, zoom=float(zoom))
    if fmt == "html":
        return report.export_html(output_path)
    if fmt == "csv":
        return report.export_csv(output_path)
    if fmt == "xls":
        return report.export_xls(output_path)
    if fmt == "xlsx":
        return report.export_xlsx(output_path)
    if fmt in ("text", "txt"):
        return report.export_text(
            output_path,
            page_width=int(text_page_width),
            page_height=int(text_page_height),
        )
    if fmt == "xml":
        return report.export_xml(output_path)
    raise ValueError("Unsupported export format: {}".format(export_format))


def preview_invoice(jrxml_path, host, port, database, user, password, trans_id):
    report = build_and_fill_invoice_report(
        jrxml_path,
        host,
        port,
        database,
        user,
        password,
        trans_id,
    )
    report.preview(title="Invoice Preview")


def print_invoice(
    jrxml_path,
    host,
    port,
    database,
    user,
    password,
    trans_id,
    copies=1,
    collate=False,
    duplex=False,
    printer_name=None,
    show_dialog=True,
):
    report = build_and_fill_invoice_report(
        jrxml_path,
        host,
        port,
        database,
        user,
        password,
        trans_id,
    )
    return report.print(
        title="Print Invoice",
        printer=printer_name,
        copies=int(copies),
        collate=bool(collate),
        duplex=bool(duplex),
        show_dialog=bool(show_dialog),
    )


def export_invoice(
    jrxml_path,
    host,
    port,
    database,
    user,
    password,
    trans_id,
    export_format,
    output_path=None,
    output_dir=None,
    zoom=2.0,
    text_page_width=120,
    text_page_height=60,
):
    report = build_and_fill_invoice_report(
        jrxml_path,
        host,
        port,
        database,
        user,
        password,
        trans_id,
    )
    return export_report(
        report,
        export_format=export_format,
        output_path=output_path,
        output_dir=output_dir,
        zoom=zoom,
        text_page_width=text_page_width,
        text_page_height=text_page_height,
    )


def report_info(jrxml_path, refresh=False):
    report = Report(jrxml_path)
    return report.info(refresh=bool(refresh))

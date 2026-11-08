# M10.1b steps

Each line is one user-visible step on the ChoreBoy display.

1. editor / ready. Did: Start Code Studio.. Saw: ready in 1955 ms; status Startup: Capability data unavailable | Syntax highlighting off. Shot: editor/01-ready.png. pass
2. customer / new-project. Did: File > New Project, name Customer card.. Saw: folder /tmp/m10_cbcs_work/projects/Customer card. Shot: customer/02-new-project.png. pass
3. customer / connection. Did: File > Settings > Connections, add SQLite data/shop.db, Test.. Saw: ✓ Connected · SQLite · 1 tables. Shot: customer/03-connection.png. pass
4. customer / from-table. Did: Build a form from customers (Record form).. Saw: Create customer form with 5 fields; picked=True; start enabled=False checked=False. Shot: customer/04-from-table.png. pass
5. customer / email-check. Did: Behavior, Add check, Email address on email.. Saw: check committed. Shot: customer/05-email-check.png. pass
6. customer / credit-check. Did: Add check Between with smallest 0 on credit_limit.. Saw: check committed. Shot: customer/06-credit-check.png. pass
7. customer / enabled-rule. Did: Enabled when on credit_limit, formula active.. Saw: committed=True outline missed (no visible outline); using the current widget. Shot: customer/07-enabled-rule.png. pass
8. customer / save. Did: Ctrl+S.. Saw: ui file ui_customer_card.py exists=True.. Shot: customer/08-save.png. pass
9. customer / your-code. Did: Select saveButton, Shift+F10, Write code for, replace pass.. Saw: method file has the body=True. . Shot: customer/09-your-code.png. pass
10. customer / preview. Did: Preview with Run behavior.. Saw: 1680x1050. Shot: customer/10-preview.png. pass
11. customer / preview-light. Did: View > Theme > light while Preview is open.. Saw: screen 1680x1050; popup black=None. Shot: customer/11-preview-light.png. pass
12. customer / preview-dark. Did: View > Theme > dark while Preview is open.. Saw: screen 1680x1050; popup black=None. Shot: customer/12-preview-dark.png. pass
13. customer / preview-high_contrast_light. Did: View > Theme > high_contrast_light while Preview is open.. Saw: screen 1680x1050; popup black=None. Shot: customer/13-preview-high_contrast_light.png. pass
14. customer / preview-high_contrast_dark. Did: View > Theme > high_contrast_dark while Preview is open.. Saw: screen 1680x1050; popup black=None. Shot: customer/14-preview-high_contrast_dark.png. pass
15. customer / entry. Did: The start checkbox is off because main.py is already the project's file. Wrote the launch the manual describes.. Saw: main.py opens CustomerCardWindow. Shot: customer/15-entry.png. pass
16. products / new-project. Did: Create and open Products with the project commands (the New Project dialog did not return once a project was open).. Saw: /tmp/m10_cbcs_work/projects/Products. Shot: products/16-new-project.png. pass
17. products / connection. Did: File > Settings > Connections, add SQLite data/shop.db, Test.. Saw: ✓ Connected · SQLite · 2 tables. Shot: products/17-connection.png. pass
18. products / from-table. Did: Build a form from products (List screen and record form).. Saw: Create product form with 4 fields and lines and a list; picked=True; start enabled=False checked=False. Shot: products/18-from-table.png. pass
19. products / filter-rule. Did: Enabled when on the search box: form.count > 0.. Saw: committed=True outline click. Shot: products/19-filter-rule.png. pass
20. products / filter-row. Did: Data panel, add a filter row.. Saw: filter add clicked. Shot: products/20-filter-row.png. pass
21. products / save. Did: Ctrl+S.. Saw: ui file ui_products.py exists=True.. Shot: products/21-save.png. pass
22. products / list-file. Did: Save also writes the list screen.. Saw: ui_products_list.py exists=True. Shot: products/22-list-file.png. pass
23. products / preview. Did: Preview the products form.. Saw: 1680x1050. Shot: products/23-preview.png. pass
24. products / entry. Did: The start checkbox is off because main.py is already the project's file. Wrote the launch the manual describes.. Saw: main.py opens ProductsListWindow. Shot: products/24-entry.png. pass
25. shop / new-project. Did: Create and open Shop desk with the project commands (the New Project dialog did not return once a project was open).. Saw: /tmp/m10_cbcs_work/projects/Shop desk. Shot: shop/25-new-project.png. pass
26. shop / main-window. Did: New form shop_desk, Main window card.. Saw: canvas up=True. Shot: shop/26-main-window.png. pass
27. shop / menus. Did: On the menu bar, type File, Edit and Help.. Saw: titles in the ui file=True. Shot: shop/27-menus.png. pass
28. shop / toolbar. Did: Form > Main window > Add toolbar.. Saw: action ran=True. Shot: shop/28-toolbar.png. pass
29. shop / tabs. Did: Insert a tab widget in the central area.. Saw: insert closed. Shot: shop/29-tabs.png. pass
30. shop / buddies-tabs. Did: F7 buddy, F8 tab order.. Saw: 1680x1050. Shot: shop/30-buddies-tabs.png. pass
31. shop / save. Did: Ctrl+S.. Saw: ui file ui_shop_desk.py exists=True.. Shot: shop/31-save.png. pass
32. shop / entry. Did: The start checkbox is off because main.py is already the project's file. Wrote the launch the manual describes.. Saw: main.py opens ShopDeskWindow. Shot: shop/32-entry.png. pass
33. customer / package. Did: Run > Package Project.. Saw: artifact /tmp/m10_cbcs_work/export/customer/customer_card_installer_v0.1.0 package_project success=True error=. Shot: customer/33-package.png. pass
34. customer / install. Did: Run the package installer (perform_install, the same call the wizard's Install button makes).. Saw: ok=True dir=/home/default/FreeCAD/Apps/customer_card. Shot: customer/34-install.png. pass
35. products / package. Did: Run > Package Project.. Saw: artifact /tmp/m10_cbcs_work/export/products/products_installer_v0.1.0 package_project success=True error=. Shot: products/35-package.png. pass
36. products / install. Did: Run the package installer (perform_install, the same call the wizard's Install button makes).. Saw: ok=True dir=/home/default/FreeCAD/Apps/products. Shot: products/36-install.png. pass
37. shop / package. Did: Run > Package Project.. Saw: artifact /tmp/m10_cbcs_work/export/shop/shop_desk_installer_v0.1.0 package_project success=True error=. Shot: shop/37-package.png. pass
38. shop / install. Did: Run the package installer (perform_install, the same call the wizard's Install button makes).. Saw: ok=True dir=/home/default/FreeCAD/Apps/shop_desk. Shot: shop/38-install.png. pass
39. customer / launcher. Did: Start the installed .desktop Exec.. Saw: pid 1427007 screen 1680x1050 . Shot: customer/39-launcher.png. pass
40. customer / use-installed. Did: Use the installed app_files window.. Saw: rc=0 ms=446. Shot: customer/40-use-installed.png. pass
41. products / launcher. Did: Start the installed .desktop Exec.. Saw: pid 1427030 screen 1680x1050 . Shot: products/41-launcher.png. pass
42. products / use-installed. Did: Use the installed app_files window.. Saw: rc=0 ms=340. Shot: products/42-use-installed.png. pass
43. shop / launcher. Did: Start the installed .desktop Exec.. Saw: pid 1427060 screen 1680x1050 . Shot: shop/43-launcher.png. pass
44. shop / use-installed. Did: Use the installed app_files window.. Saw: rc=0 ms=367. Shot: shop/44-use-installed.png. pass

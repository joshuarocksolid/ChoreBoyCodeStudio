import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.sql.Connection;
import java.sql.Date;
import java.sql.DriverManager;
import java.sql.Time;
import java.sql.Timestamp;
import java.util.Base64;
import java.util.HashMap;
import javax.imageio.ImageIO;
import net.sf.jasperreports.engine.JREmptyDataSource;
import net.sf.jasperreports.engine.JRParameter;
import net.sf.jasperreports.engine.JasperCompileManager;
import net.sf.jasperreports.engine.JasperExportManager;
import net.sf.jasperreports.engine.JasperFillManager;
import net.sf.jasperreports.engine.JasperPrint;
import net.sf.jasperreports.engine.JasperReport;
import net.sf.jasperreports.engine.data.JRCsvDataSource;
import net.sf.jasperreports.engine.data.JsonDataSource;
import net.sf.jasperreports.engine.export.HtmlExporter;
import net.sf.jasperreports.engine.export.JRCsvExporter;
import net.sf.jasperreports.engine.export.JRGraphics2DExporter;
import net.sf.jasperreports.engine.export.JRTextExporter;
import net.sf.jasperreports.engine.export.JRXmlExporter;
import net.sf.jasperreports.engine.export.JRXlsExporter;
import net.sf.jasperreports.engine.export.ooxml.JRXlsxExporter;
import net.sf.jasperreports.engine.util.JRLoader;
import net.sf.jasperreports.export.SimpleExporterInput;
import net.sf.jasperreports.export.SimpleHtmlExporterOutput;
import net.sf.jasperreports.export.SimpleGraphics2DExporterOutput;
import net.sf.jasperreports.export.SimpleGraphics2DReportConfiguration;
import net.sf.jasperreports.export.SimpleOutputStreamExporterOutput;
import net.sf.jasperreports.export.SimpleTextReportConfiguration;
import net.sf.jasperreports.export.SimpleWriterExporterOutput;
import net.sf.jasperreports.export.SimpleXmlExporterOutput;
import net.sf.jasperreports.export.SimpleXlsxReportConfiguration;
import net.sf.jasperreports.export.SimpleXlsReportConfiguration;

public class JasperBridge {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static JasperPrint lastPrint = null;
    private static JasperReport lastReport = null;

    public static void main(String[] args) {
        String action = "unknown";
        try {
            if (args.length < 1) {
                throw new IllegalArgumentException("Missing JSON command argument");
            }

            JsonNode parsed = MAPPER.readTree(args[0]);
            if (!(parsed instanceof ObjectNode)) {
                throw new IllegalArgumentException("Command must be a JSON object");
            }
            ObjectNode command = (ObjectNode) parsed;
            action = requiredText(command, "action");

            if ("compile".equals(action)) {
                handleCompile(command);
            } else if ("fill_empty".equals(action)) {
                handleFillEmpty(command);
            } else if ("fill_jdbc".equals(action)) {
                handleFillJdbc(command);
            } else if ("fill_json".equals(action)) {
                handleFillJson(command);
            } else if ("fill_csv".equals(action)) {
                handleFillCsv(command);
            } else if ("export_pdf".equals(action)) {
                handleExportPdf(command);
            } else if ("export_png".equals(action)) {
                handleExportPng(command);
            } else if ("export_html".equals(action)) {
                handleExportHtml(command);
            } else if ("export_csv".equals(action)) {
                handleExportCsv(command);
            } else if ("export_xls".equals(action)) {
                handleExportXls(command);
            } else if ("export_text".equals(action)) {
                handleExportText(command);
            } else if ("export_xml".equals(action)) {
                handleExportXml(command);
            } else if ("export_xlsx".equals(action)) {
                handleExportXlsx(command);
            } else if ("fill_and_export".equals(action)) {
                handleFillAndExport(command);
            } else if ("info".equals(action)) {
                handleInfo(command);
            } else {
                throw new IllegalArgumentException("Unsupported action: " + action);
            }
        } catch (Exception e) {
            respondError(action, e);
        }
    }

    private static void handleCompile(ObjectNode command) throws Exception {
        String jrxml = requiredText(command, "jrxml");
        String output = optionalText(command, "output");
        if (output == null || output.length() == 0) {
            if (jrxml.endsWith(".jrxml")) {
                output = jrxml.substring(0, jrxml.length() - ".jrxml".length()) + ".jasper";
            } else {
                output = jrxml + ".jasper";
            }
        }

        File outputFile = new File(output).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }

        JasperCompileManager.compileReportToFile(jrxml, outputFile.getAbsolutePath());
        lastReport = (JasperReport) JRLoader.loadObjectFromFile(outputFile.getAbsolutePath());

        ObjectNode response = baseOk("compile");
        response.put("jasper_path", outputFile.getAbsolutePath());
        response.put("size", outputFile.length());
        respond(response);
    }

    private static void handleFillEmpty(ObjectNode command) throws Exception {
        String reportPath = requiredText(command, "jrxml_or_jasper");
        JasperReport report = loadOrCompile(reportPath);
        HashMap<String, Object> params = deserializeParams(command.get("params"));
        JasperPrint print = JasperFillManager.fillReport(report, params, new JREmptyDataSource());
        lastReport = report;
        lastPrint = print;

        ObjectNode response = baseOk("fill_empty");
        response.put("page_count", print.getPages().size());
        respond(response);
    }

    private static void handleFillJdbc(ObjectNode command) throws Exception {
        String reportPath = requiredText(command, "jrxml_or_jasper");
        String jdbcUrl = requiredText(command, "jdbc_url");
        String user = requiredText(command, "user");
        String pass = requiredText(command, "pass");

        JasperReport report = loadOrCompile(reportPath);
        HashMap<String, Object> params = deserializeParams(command.get("params"));

        Class.forName("org.postgresql.Driver");
        Connection connection = DriverManager.getConnection(jdbcUrl, user, pass);
        try {
            JasperPrint print = JasperFillManager.fillReport(report, params, connection);
            lastReport = report;
            lastPrint = print;

            ObjectNode response = baseOk("fill_jdbc");
            response.put("page_count", print.getPages().size());
            respond(response);
        } finally {
            connection.close();
        }
    }

    private static void handleFillJson(ObjectNode command) throws Exception {
        String reportPath = requiredText(command, "jrxml_or_jasper");
        String jsonFile = requiredText(command, "json_file");
        String selectExpression = optionalText(command, "select_expression");

        JasperReport report = loadOrCompile(reportPath);
        HashMap<String, Object> params = deserializeParams(command.get("params"));

        InputStream stream = new FileInputStream(jsonFile);
        try {
            JsonDataSource dataSource;
            if (selectExpression != null && selectExpression.length() > 0) {
                dataSource = new JsonDataSource(stream, selectExpression);
            } else {
                dataSource = new JsonDataSource(stream);
            }
            JasperPrint print = JasperFillManager.fillReport(report, params, dataSource);
            lastReport = report;
            lastPrint = print;
            dataSource.close();

            ObjectNode response = baseOk("fill_json");
            response.put("page_count", print.getPages().size());
            respond(response);
        } finally {
            stream.close();
        }
    }

    private static void handleFillCsv(ObjectNode command) throws Exception {
        String reportPath = requiredText(command, "jrxml_or_jasper");
        String csvFile = requiredText(command, "csv_file");

        JasperReport report = loadOrCompile(reportPath);
        HashMap<String, Object> params = deserializeParams(command.get("params"));
        JRCsvDataSource dataSource = new JRCsvDataSource(new File(csvFile));

        JasperPrint print = JasperFillManager.fillReport(report, params, dataSource);
        lastReport = report;
        lastPrint = print;
        dataSource.close();

        ObjectNode response = baseOk("fill_csv");
        response.put("page_count", print.getPages().size());
        respond(response);
    }

    private static void handleExportPdf(ObjectNode command) throws Exception {
        ensureFilled("export_pdf");
        String outputPath = requiredText(command, "output_path");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }

        JasperExportManager.exportReportToPdfFile(lastPrint, outputFile.getAbsolutePath());
        ObjectNode response = baseOk("export_pdf");
        response.put("output_path", outputFile.getAbsolutePath());
        response.put("size", outputFile.length());
        respond(response);
    }

    private static void handleExportPng(ObjectNode command) throws Exception {
        ensureFilled("export_png");
        String outputDir = requiredText(command, "output_dir");
        double zoomDouble = command.has("zoom") ? command.get("zoom").asDouble(1.0) : 1.0;
        float zoom = (float) zoomDouble;
        if (zoom <= 0.0f) {
            throw new IllegalArgumentException("zoom must be > 0");
        }

        File dir = new File(outputDir).getAbsoluteFile();
        dir.mkdirs();

        int pageCount = lastPrint.getPages().size();
        ArrayNode pages = MAPPER.createArrayNode();
        for (int i = 0; i < pageCount; i++) {
            int width = Math.round(lastPrint.getPageWidth() * zoom);
            int height = Math.round(lastPrint.getPageHeight() * zoom);

            BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
            Graphics2D g2d = image.createGraphics();
            g2d.setColor(Color.WHITE);
            g2d.fillRect(0, 0, width, height);

            JRGraphics2DExporter exporter = new JRGraphics2DExporter();
            exporter.setExporterInput(new SimpleExporterInput(lastPrint));

            SimpleGraphics2DReportConfiguration configuration = new SimpleGraphics2DReportConfiguration();
            configuration.setPageIndex(i);
            configuration.setZoomRatio(zoom);
            exporter.setConfiguration(configuration);

            SimpleGraphics2DExporterOutput output = new SimpleGraphics2DExporterOutput();
            output.setGraphics2D(g2d);
            exporter.setExporterOutput(output);

            exporter.exportReport();
            g2d.dispose();

            String fileName = String.format("page_%03d.png", i + 1);
            File pngFile = new File(dir, fileName).getAbsoluteFile();
            ImageIO.write(image, "png", pngFile);
            pages.add(pngFile.getAbsolutePath());
        }

        ObjectNode response = baseOk("export_png");
        response.set("pages", pages);
        response.put("count", pageCount);
        respond(response);
    }

    private static void handleExportHtml(ObjectNode command) throws Exception {
        ensureFilled("export_html");
        String outputPath = requiredText(command, "output_path");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }

        HtmlExporter exporter = new HtmlExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleHtmlExporterOutput(outputFile));
        exporter.exportReport();

        ObjectNode response = baseOk("export_html");
        response.put("output_path", outputFile.getAbsolutePath());
        response.put("size", outputFile.length());
        respond(response);
    }

    private static void handleExportCsv(ObjectNode command) throws Exception {
        ensureFilled("export_csv");
        String outputPath = requiredText(command, "output_path");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }

        JRCsvExporter exporter = new JRCsvExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleWriterExporterOutput(outputFile));
        exporter.exportReport();

        ObjectNode response = baseOk("export_csv");
        response.put("output_path", outputFile.getAbsolutePath());
        response.put("size", outputFile.length());
        respond(response);
    }

    private static void handleExportXls(ObjectNode command) throws Exception {
        ensureFilled("export_xls");
        String outputPath = requiredText(command, "output_path");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }

        JRXlsExporter exporter = new JRXlsExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleOutputStreamExporterOutput(outputFile));
        exporter.setConfiguration(new SimpleXlsReportConfiguration());
        exporter.exportReport();

        ObjectNode response = baseOk("export_xls");
        response.put("output_path", outputFile.getAbsolutePath());
        response.put("size", outputFile.length());
        respond(response);
    }

    private static void handleExportText(ObjectNode command) throws Exception {
        ensureFilled("export_text");
        String outputPath = requiredText(command, "output_path");
        int pageWidth = command.has("page_width") ? command.get("page_width").asInt(120) : 120;
        int pageHeight = command.has("page_height") ? command.get("page_height").asInt(60) : 60;
        if (pageWidth <= 0 || pageHeight <= 0) {
            throw new IllegalArgumentException("page_width and page_height must be > 0");
        }

        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }

        JRTextExporter exporter = new JRTextExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleWriterExporterOutput(outputFile));
        SimpleTextReportConfiguration configuration = new SimpleTextReportConfiguration();
        configuration.setPageWidthInChars(Integer.valueOf(pageWidth));
        configuration.setPageHeightInChars(Integer.valueOf(pageHeight));
        exporter.setConfiguration(configuration);
        exporter.exportReport();

        ObjectNode response = baseOk("export_text");
        response.put("output_path", outputFile.getAbsolutePath());
        response.put("size", outputFile.length());
        respond(response);
    }

    private static void handleExportXml(ObjectNode command) throws Exception {
        ensureFilled("export_xml");
        String outputPath = requiredText(command, "output_path");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }

        JRXmlExporter exporter = new JRXmlExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleXmlExporterOutput(outputFile));
        exporter.exportReport();

        ObjectNode response = baseOk("export_xml");
        response.put("output_path", outputFile.getAbsolutePath());
        response.put("size", outputFile.length());
        respond(response);
    }

    private static void handleExportXlsx(ObjectNode command) throws Exception {
        ensureFilled("export_xlsx");
        String outputPath = requiredText(command, "output_path");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }

        JRXlsxExporter exporter = new JRXlsxExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleOutputStreamExporterOutput(outputFile));
        exporter.setConfiguration(new SimpleXlsxReportConfiguration());
        exporter.exportReport();

        ObjectNode response = baseOk("export_xlsx");
        response.put("output_path", outputFile.getAbsolutePath());
        response.put("size", outputFile.length());
        respond(response);
    }

    private static void handleFillAndExport(ObjectNode command) throws Exception {
        JasperPrint print = fillFromCommand(command);
        JsonNode exportsNode = command.get("exports");
        if (!(exportsNode instanceof ArrayNode)) {
            throw new IllegalArgumentException("exports must be an array");
        }

        ArrayNode exportSpecs = (ArrayNode) exportsNode;
        ArrayNode exports = MAPPER.createArrayNode();
        for (int i = 0; i < exportSpecs.size(); i++) {
            JsonNode specNode = exportSpecs.get(i);
            if (!(specNode instanceof ObjectNode)) {
                throw new IllegalArgumentException("Each export spec must be an object");
            }
            ObjectNode spec = (ObjectNode) specNode;
            exports.add(exportBySpec(spec));
        }

        ObjectNode response = baseOk("fill_and_export");
        response.put("page_count", print.getPages().size());
        response.set("exports", exports);
        respond(response);
    }

    private static JasperPrint fillFromCommand(ObjectNode command) throws Exception {
        String reportPath = requiredText(command, "jrxml_or_jasper");
        JasperReport report = loadOrCompile(reportPath);
        HashMap<String, Object> params = deserializeParams(command.get("params"));

        JasperPrint print;
        if (command.has("json_file")) {
            String jsonFile = requiredText(command, "json_file");
            String selectExpression = optionalText(command, "select_expression");
            InputStream stream = new FileInputStream(jsonFile);
            try {
                JsonDataSource dataSource;
                if (selectExpression != null && selectExpression.length() > 0) {
                    dataSource = new JsonDataSource(stream, selectExpression);
                } else {
                    dataSource = new JsonDataSource(stream);
                }
                print = JasperFillManager.fillReport(report, params, dataSource);
                dataSource.close();
            } finally {
                stream.close();
            }
        } else if (command.has("csv_file")) {
            String csvFile = requiredText(command, "csv_file");
            JRCsvDataSource dataSource = new JRCsvDataSource(new File(csvFile));
            print = JasperFillManager.fillReport(report, params, dataSource);
            dataSource.close();
        } else if (command.has("jdbc_url")) {
            String jdbcUrl = requiredText(command, "jdbc_url");
            String user = requiredText(command, "user");
            String pass = requiredText(command, "pass");
            Class.forName("org.postgresql.Driver");
            Connection connection = DriverManager.getConnection(jdbcUrl, user, pass);
            try {
                print = JasperFillManager.fillReport(report, params, connection);
            } finally {
                connection.close();
            }
        } else {
            print = JasperFillManager.fillReport(report, params, new JREmptyDataSource());
        }

        lastReport = report;
        lastPrint = print;
        return print;
    }

    private static ObjectNode exportBySpec(ObjectNode spec) throws Exception {
        String format = requiredText(spec, "format").toLowerCase();
        if ("pdf".equals(format)) {
            return exportPdfInternal(requiredText(spec, "output_path"));
        }
        if ("png".equals(format)) {
            double zoomDouble = spec.has("zoom") ? spec.get("zoom").asDouble(1.0) : 1.0;
            return exportPngInternal(requiredText(spec, "output_dir"), (float) zoomDouble);
        }
        if ("html".equals(format)) {
            return exportHtmlInternal(requiredText(spec, "output_path"));
        }
        if ("csv".equals(format)) {
            return exportCsvInternal(requiredText(spec, "output_path"));
        }
        if ("xls".equals(format)) {
            return exportXlsInternal(requiredText(spec, "output_path"));
        }
        if ("xlsx".equals(format)) {
            return exportXlsxInternal(requiredText(spec, "output_path"));
        }
        if ("text".equals(format) || "txt".equals(format)) {
            int pageWidth = spec.has("page_width") ? spec.get("page_width").asInt(120) : 120;
            int pageHeight = spec.has("page_height") ? spec.get("page_height").asInt(60) : 60;
            return exportTextInternal(requiredText(spec, "output_path"), pageWidth, pageHeight);
        }
        if ("xml".equals(format)) {
            return exportXmlInternal(requiredText(spec, "output_path"));
        }
        throw new IllegalArgumentException("Unsupported export format: " + format);
    }

    private static ObjectNode exportPdfInternal(String outputPath) throws Exception {
        ensureFilled("export_pdf");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }
        JasperExportManager.exportReportToPdfFile(lastPrint, outputFile.getAbsolutePath());
        ObjectNode result = MAPPER.createObjectNode();
        result.put("format", "pdf");
        result.put("output_path", outputFile.getAbsolutePath());
        result.put("size", outputFile.length());
        return result;
    }

    private static ObjectNode exportPngInternal(String outputDir, float zoom) throws Exception {
        ensureFilled("export_png");
        if (zoom <= 0.0f) {
            throw new IllegalArgumentException("zoom must be > 0");
        }
        File dir = new File(outputDir).getAbsoluteFile();
        dir.mkdirs();

        int pageCount = lastPrint.getPages().size();
        ArrayNode pages = MAPPER.createArrayNode();
        for (int i = 0; i < pageCount; i++) {
            int width = Math.round(lastPrint.getPageWidth() * zoom);
            int height = Math.round(lastPrint.getPageHeight() * zoom);
            BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
            Graphics2D g2d = image.createGraphics();
            g2d.setColor(Color.WHITE);
            g2d.fillRect(0, 0, width, height);

            JRGraphics2DExporter exporter = new JRGraphics2DExporter();
            exporter.setExporterInput(new SimpleExporterInput(lastPrint));
            SimpleGraphics2DReportConfiguration configuration = new SimpleGraphics2DReportConfiguration();
            configuration.setPageIndex(i);
            configuration.setZoomRatio(zoom);
            exporter.setConfiguration(configuration);
            SimpleGraphics2DExporterOutput output = new SimpleGraphics2DExporterOutput();
            output.setGraphics2D(g2d);
            exporter.setExporterOutput(output);
            exporter.exportReport();
            g2d.dispose();

            String fileName = String.format("page_%03d.png", i + 1);
            File pngFile = new File(dir, fileName).getAbsoluteFile();
            ImageIO.write(image, "png", pngFile);
            pages.add(pngFile.getAbsolutePath());
        }

        ObjectNode result = MAPPER.createObjectNode();
        result.put("format", "png");
        result.put("output_dir", dir.getAbsolutePath());
        result.set("pages", pages);
        result.put("count", pageCount);
        return result;
    }

    private static ObjectNode exportHtmlInternal(String outputPath) throws Exception {
        ensureFilled("export_html");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }
        HtmlExporter exporter = new HtmlExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleHtmlExporterOutput(outputFile));
        exporter.exportReport();

        ObjectNode result = MAPPER.createObjectNode();
        result.put("format", "html");
        result.put("output_path", outputFile.getAbsolutePath());
        result.put("size", outputFile.length());
        return result;
    }

    private static ObjectNode exportCsvInternal(String outputPath) throws Exception {
        ensureFilled("export_csv");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }
        JRCsvExporter exporter = new JRCsvExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleWriterExporterOutput(outputFile));
        exporter.exportReport();

        ObjectNode result = MAPPER.createObjectNode();
        result.put("format", "csv");
        result.put("output_path", outputFile.getAbsolutePath());
        result.put("size", outputFile.length());
        return result;
    }

    private static ObjectNode exportXlsInternal(String outputPath) throws Exception {
        ensureFilled("export_xls");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }
        JRXlsExporter exporter = new JRXlsExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleOutputStreamExporterOutput(outputFile));
        exporter.setConfiguration(new SimpleXlsReportConfiguration());
        exporter.exportReport();

        ObjectNode result = MAPPER.createObjectNode();
        result.put("format", "xls");
        result.put("output_path", outputFile.getAbsolutePath());
        result.put("size", outputFile.length());
        return result;
    }

    private static ObjectNode exportXlsxInternal(String outputPath) throws Exception {
        ensureFilled("export_xlsx");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }
        JRXlsxExporter exporter = new JRXlsxExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleOutputStreamExporterOutput(outputFile));
        exporter.setConfiguration(new SimpleXlsxReportConfiguration());
        exporter.exportReport();

        ObjectNode result = MAPPER.createObjectNode();
        result.put("format", "xlsx");
        result.put("output_path", outputFile.getAbsolutePath());
        result.put("size", outputFile.length());
        return result;
    }

    private static ObjectNode exportTextInternal(String outputPath, int pageWidth, int pageHeight) throws Exception {
        ensureFilled("export_text");
        if (pageWidth <= 0 || pageHeight <= 0) {
            throw new IllegalArgumentException("page_width and page_height must be > 0");
        }
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }
        JRTextExporter exporter = new JRTextExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleWriterExporterOutput(outputFile));
        SimpleTextReportConfiguration configuration = new SimpleTextReportConfiguration();
        configuration.setPageWidthInChars(Integer.valueOf(pageWidth));
        configuration.setPageHeightInChars(Integer.valueOf(pageHeight));
        exporter.setConfiguration(configuration);
        exporter.exportReport();

        ObjectNode result = MAPPER.createObjectNode();
        result.put("format", "text");
        result.put("output_path", outputFile.getAbsolutePath());
        result.put("size", outputFile.length());
        return result;
    }

    private static ObjectNode exportXmlInternal(String outputPath) throws Exception {
        ensureFilled("export_xml");
        File outputFile = new File(outputPath).getAbsoluteFile();
        File parent = outputFile.getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }
        JRXmlExporter exporter = new JRXmlExporter();
        exporter.setExporterInput(new SimpleExporterInput(lastPrint));
        exporter.setExporterOutput(new SimpleXmlExporterOutput(outputFile));
        exporter.exportReport();

        ObjectNode result = MAPPER.createObjectNode();
        result.put("format", "xml");
        result.put("output_path", outputFile.getAbsolutePath());
        result.put("size", outputFile.length());
        return result;
    }

    private static void handleInfo(ObjectNode command) throws Exception {
        String reportPath = requiredText(command, "jrxml_or_jasper");
        JasperReport report = loadOrCompile(reportPath);

        ArrayNode parameters = MAPPER.createArrayNode();
        JRParameter[] reportParameters = report.getParameters();
        for (int i = 0; i < reportParameters.length; i++) {
            JRParameter parameter = reportParameters[i];
            ObjectNode parameterNode = MAPPER.createObjectNode();
            parameterNode.put("name", parameter.getName());
            Class<?> valueClass = parameter.getValueClass();
            parameterNode.put("type", valueClass != null ? valueClass.getName() : "unknown");
            parameterNode.put("for_prompting", parameter.isForPrompting());
            parameterNode.put("system_defined", parameter.isSystemDefined());
            parameterNode.put("value_class_name", parameter.getValueClassName());
            parameterNode.put("has_default", parameter.getDefaultValueExpression() != null);
            if (parameter.getDefaultValueExpression() != null) {
                parameterNode.put("default_expression", parameter.getDefaultValueExpression().getText());
            } else {
                parameterNode.putNull("default_expression");
            }
            parameters.add(parameterNode);
        }

        ArrayNode fields = MAPPER.createArrayNode();
        net.sf.jasperreports.engine.JRField[] reportFields = report.getFields();
        for (int i = 0; i < reportFields.length; i++) {
            net.sf.jasperreports.engine.JRField field = reportFields[i];
            ObjectNode fieldNode = MAPPER.createObjectNode();
            fieldNode.put("name", field.getName());
            fieldNode.put("type", field.getValueClassName());
            fields.add(fieldNode);
        }

        ObjectNode response = baseOk("info");
        response.put("name", report.getName());
        response.put("page_width", report.getPageWidth());
        response.put("page_height", report.getPageHeight());
        response.set("parameters", parameters);
        response.set("fields", fields);
        if (report.getQuery() != null) {
            response.put("query", report.getQuery().getText());
            response.put("query_language", report.getQuery().getLanguage());
        } else {
            response.putNull("query");
            response.putNull("query_language");
        }
        respond(response);
    }

    private static JasperReport loadOrCompile(String path) throws Exception {
        if (path.endsWith(".jrxml")) {
            return JasperCompileManager.compileReport(path);
        }
        if (path.endsWith(".jasper")) {
            return (JasperReport) JRLoader.loadObjectFromFile(path);
        }
        throw new IllegalArgumentException("Report path must end with .jrxml or .jasper: " + path);
    }

    private static void ensureFilled(String action) {
        if (lastPrint == null) {
            throw new IllegalStateException(
                action + " requires a filled report. Call fill_empty, fill_jdbc, fill_json, or fill_csv first."
            );
        }
    }

    private static HashMap<String, Object> deserializeParams(JsonNode paramsNode) throws Exception {
        HashMap<String, Object> params = new HashMap<String, Object>();
        if (paramsNode == null || paramsNode.isNull()) {
            return params;
        }
        if (!(paramsNode instanceof ArrayNode)) {
            throw new IllegalArgumentException("params must be a JSON array");
        }

        ArrayNode array = (ArrayNode) paramsNode;
        for (int i = 0; i < array.size(); i++) {
            JsonNode node = array.get(i);
            String name = requiredText(node, "name");
            String type = requiredText(node, "type");
            JsonNode valueNode = node.get("value");
            if (valueNode == null || valueNode.isNull()) {
                throw new IllegalArgumentException("Parameter value cannot be null for " + name);
            }

            Object mappedValue;
            if ("string".equals(type)) {
                mappedValue = valueNode.asText();
            } else if ("integer".equals(type)) {
                mappedValue = Integer.valueOf(valueNode.intValue());
            } else if ("long".equals(type)) {
                mappedValue = valueNode.longValue();
            } else if ("double".equals(type)) {
                mappedValue = valueNode.doubleValue();
            } else if ("boolean".equals(type)) {
                mappedValue = valueNode.asBoolean();
            } else if ("bytes".equals(type)) {
                mappedValue = Base64.getDecoder().decode(valueNode.asText());
            } else if ("image_path".equals(type)) {
                File imageFile = new File(valueNode.asText());
                BufferedImage image = ImageIO.read(imageFile);
                if (image == null) {
                    throw new IllegalArgumentException("Could not read image from path: " + imageFile);
                }
                mappedValue = image;
            } else if ("image_bytes".equals(type)) {
                byte[] imageBytes = Base64.getDecoder().decode(valueNode.asText());
                BufferedImage image = ImageIO.read(new ByteArrayInputStream(imageBytes));
                if (image == null) {
                    throw new IllegalArgumentException("Could not decode image bytes for parameter: " + name);
                }
                mappedValue = image;
            } else if ("date".equals(type)) {
                mappedValue = Date.valueOf(valueNode.asText());
            } else if ("time".equals(type)) {
                mappedValue = Time.valueOf(valueNode.asText());
            } else if ("datetime".equals(type)) {
                String text = valueNode.asText().replace("T", " ");
                mappedValue = Timestamp.valueOf(text);
            } else {
                throw new IllegalArgumentException("Unsupported parameter type: " + type);
            }

            params.put(name, mappedValue);
        }
        return params;
    }

    private static ObjectNode baseOk(String action) {
        ObjectNode response = MAPPER.createObjectNode();
        response.put("status", "ok");
        response.put("action", action);
        return response;
    }

    private static String requiredText(JsonNode node, String key) {
        JsonNode value = node.get(key);
        if (value == null || value.isNull()) {
            throw new IllegalArgumentException("Missing required field: " + key);
        }
        String text = value.asText();
        if (text == null || text.length() == 0) {
            throw new IllegalArgumentException("Field must be non-empty: " + key);
        }
        return text;
    }

    private static String optionalText(JsonNode node, String key) {
        JsonNode value = node.get(key);
        if (value == null || value.isNull()) {
            return null;
        }
        return value.asText();
    }

    private static void respond(ObjectNode response) {
        try {
            System.out.println(MAPPER.writeValueAsString(response));
        } catch (Exception e) {
            e.printStackTrace(System.err);
            System.out.println("{\"status\":\"error\",\"action\":\"response\",\"error_type\":\"java.lang.RuntimeException\",\"error_message\":\"Failed to serialize JSON response\",\"stacktrace\":\"\"}");
        }
    }

    private static void respondError(String action, Exception exception) {
        exception.printStackTrace(System.err);

        ObjectNode response = MAPPER.createObjectNode();
        response.put("status", "error");
        response.put("action", action);
        response.put("error_type", exception.getClass().getName());
        String message = exception.getMessage();
        response.put("error_message", message == null ? exception.toString() : message);

        StringWriter stringWriter = new StringWriter();
        PrintWriter printWriter = new PrintWriter(stringWriter);
        exception.printStackTrace(printWriter);
        printWriter.flush();
        response.put("stacktrace", stringWriter.toString());

        respond(response);
    }
}

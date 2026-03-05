import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.io.File;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.HashMap;
import javax.imageio.ImageIO;

import net.sf.jasperreports.engine.JREmptyDataSource;
import net.sf.jasperreports.engine.JasperCompileManager;
import net.sf.jasperreports.engine.JasperExportManager;
import net.sf.jasperreports.engine.JasperFillManager;
import net.sf.jasperreports.engine.JasperPrint;
import net.sf.jasperreports.engine.JasperReport;
import net.sf.jasperreports.engine.export.JRGraphics2DExporter;
import net.sf.jasperreports.export.SimpleExporterInput;
import net.sf.jasperreports.export.SimpleGraphics2DExporterOutput;
import net.sf.jasperreports.export.SimpleGraphics2DReportConfiguration;

public class JasperFillExport {
    public static void main(String[] args) {
        if (args.length < 3) {
            System.out.println("FILL_ERROR|Usage: JasperFillExport <input.jrxml> <output_dir> [jdbc_url user pass]");
            System.exit(1);
        }

        String jrxmlPath = args[0];
        String outputDir = args[1];
        String mode = args[2];

        String jdbcUrl = args.length > 3 ? args[3] : null;
        String jdbcUser = args.length > 4 ? args[4] : null;
        String jdbcPass = args.length > 5 ? args[5] : null;

        new File(outputDir).mkdirs();

        try {
            System.out.println("FILL_COMPILE_START|" + jrxmlPath);
            JasperReport report = JasperCompileManager.compileReport(jrxmlPath);
            System.out.println("FILL_COMPILE_OK|compiled in memory");

            HashMap<String, Object> params = new HashMap<String, Object>();
            JasperPrint print;

            if ("jdbc".equals(mode) && jdbcUrl != null) {
                System.out.println("FILL_MODE|jdbc " + jdbcUrl);
                Class.forName("org.postgresql.Driver");
                Connection conn = DriverManager.getConnection(jdbcUrl, jdbcUser, jdbcPass);
                print = JasperFillManager.fillReport(report, params, conn);
                conn.close();
            } else {
                System.out.println("FILL_MODE|empty_datasource");
                print = JasperFillManager.fillReport(report, params, new JREmptyDataSource());
            }

            int pageCount = print.getPages().size();
            System.out.println("FILL_OK|" + pageCount + " pages");

            String baseName = new File(jrxmlPath).getName().replaceAll("\\.jrxml$", "");

            String pdfPath = outputDir + "/" + baseName + ".pdf";
            JasperExportManager.exportReportToPdfFile(print, pdfPath);
            long pdfSize = new File(pdfPath).length();
            System.out.println("EXPORT_PDF_OK|" + pdfPath + " (" + pdfSize + " bytes)");

            for (int i = 0; i < pageCount; i++) {
                int pageWidth = print.getPageWidth();
                int pageHeight = print.getPageHeight();
                float zoom = 2.0f;
                int imgWidth = (int)(pageWidth * zoom);
                int imgHeight = (int)(pageHeight * zoom);

                BufferedImage img = new BufferedImage(imgWidth, imgHeight, BufferedImage.TYPE_INT_RGB);
                Graphics2D g2d = img.createGraphics();
                g2d.setColor(Color.WHITE);
                g2d.fillRect(0, 0, imgWidth, imgHeight);

                JRGraphics2DExporter exporter = new JRGraphics2DExporter();
                exporter.setExporterInput(new SimpleExporterInput(print));

                SimpleGraphics2DReportConfiguration config = new SimpleGraphics2DReportConfiguration();
                config.setPageIndex(i);
                config.setZoomRatio(zoom);
                exporter.setConfiguration(config);

                SimpleGraphics2DExporterOutput output = new SimpleGraphics2DExporterOutput();
                output.setGraphics2D(g2d);
                exporter.setExporterOutput(output);

                exporter.exportReport();
                g2d.dispose();

                String pngPath = outputDir + "/" + baseName + "_page_" + (i + 1) + ".png";
                ImageIO.write(img, "png", new File(pngPath));
                long pngSize = new File(pngPath).length();
                System.out.println("EXPORT_PNG_OK|" + pngPath + " (" + pngSize + " bytes)");
            }

            System.out.println("FILL_EXPORT_DONE|" + baseName);
        } catch (Exception e) {
            System.out.println("FILL_FAIL|" + e.getClass().getName() + ": " + e.getMessage());
            e.printStackTrace(System.err);
            System.exit(1);
        }
    }
}

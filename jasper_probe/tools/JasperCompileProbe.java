import net.sf.jasperreports.engine.JasperCompileManager;

public class JasperCompileProbe {
    public static void main(String[] args) {
        if (args.length < 2) {
            System.out.println("COMPILE_ERROR|Usage: JasperCompileProbe <input.jrxml> <output.jasper>");
            System.exit(1);
        }
        String jrxmlPath = args[0];
        String jasperPath = args[1];

        try {
            System.out.println("COMPILE_START|" + jrxmlPath);
            JasperCompileManager.compileReportToFile(jrxmlPath, jasperPath);
            System.out.println("COMPILE_OK|" + jasperPath);
        } catch (Exception e) {
            System.out.println("COMPILE_FAIL|" + e.getClass().getName() + ": " + e.getMessage());
            e.printStackTrace(System.err);
            System.exit(1);
        }
    }
}

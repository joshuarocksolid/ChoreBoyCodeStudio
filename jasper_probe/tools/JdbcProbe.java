import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

public class JdbcProbe {
    public static void main(String[] args) {
        if (args.length < 5) {
            System.out.println("JDBC_ERROR|Usage: JdbcProbe <host> <port> <user> <pass> <db>");
            System.exit(1);
        }
        String host = args[0];
        String port = args[1];
        String user = args[2];
        String pass = args[3];
        String db   = args[4];
        String url  = "jdbc:postgresql://" + host + ":" + port + "/" + db;

        try {
            Class.forName("org.postgresql.Driver");
            System.out.println("JDBC_DRIVER_OK|org.postgresql.Driver loaded");
        } catch (Exception e) {
            System.out.println("JDBC_DRIVER_FAIL|" + e.getMessage());
            System.exit(1);
        }

        Connection conn = null;
        try {
            conn = DriverManager.getConnection(url, user, pass);
            System.out.println("JDBC_CONNECT_OK|" + url);
        } catch (Exception e) {
            System.out.println("JDBC_CONNECT_FAIL|" + e.getMessage());
            System.exit(1);
        }

        try {
            Statement st = conn.createStatement();
            ResultSet rs = st.executeQuery("SELECT version()");
            if (rs.next()) {
                String ver = rs.getString(1);
                if (ver.length() > 100) ver = ver.substring(0, 100);
                System.out.println("JDBC_VERSION_OK|" + ver);
            }
            rs.close();
            st.close();
        } catch (Exception e) {
            System.out.println("JDBC_VERSION_FAIL|" + e.getMessage());
        }

        try {
            Statement st = conn.createStatement();
            ResultSet rs = st.executeQuery("SELECT 1 AS probe_check");
            if (rs.next()) {
                System.out.println("JDBC_SELECT1_OK|" + rs.getInt(1));
            }
            rs.close();
            st.close();
        } catch (Exception e) {
            System.out.println("JDBC_SELECT1_FAIL|" + e.getMessage());
        }

        try {
            Statement st = conn.createStatement();
            ResultSet rs = st.executeQuery("SELECT current_database(), current_user");
            if (rs.next()) {
                System.out.println("JDBC_CURRENT_OK|db=" + rs.getString(1) + ",user=" + rs.getString(2));
            }
            rs.close();
            st.close();
        } catch (Exception e) {
            System.out.println("JDBC_CURRENT_FAIL|" + e.getMessage());
        }

        try {
            Statement st = conn.createStatement();
            ResultSet rs = st.executeQuery(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'");
            if (rs.next()) {
                System.out.println("JDBC_TABLE_COUNT_OK|" + rs.getInt(1) + " public tables");
            }
            rs.close();
            st.close();
        } catch (Exception e) {
            System.out.println("JDBC_TABLE_COUNT_FAIL|" + e.getMessage());
        }

        try {
            conn.close();
            System.out.println("JDBC_CLOSE_OK|connection closed");
        } catch (Exception e) {
            System.out.println("JDBC_CLOSE_FAIL|" + e.getMessage());
        }
    }
}

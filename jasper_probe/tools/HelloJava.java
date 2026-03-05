public class HelloJava {
    public static void main(String[] args) {
        System.out.println("HELLO_JAVA_OK|" +
            System.getProperty("java.version") + "|" +
            System.getProperty("java.vendor") + "|" +
            System.getProperty("os.name") + "|" +
            System.getProperty("os.arch"));
    }
}

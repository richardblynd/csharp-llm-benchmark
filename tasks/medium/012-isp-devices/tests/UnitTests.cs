using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void defines_small_capability_interfaces()
    {
        Assert.IsTrue(typeof(global::IPrinter).IsInterface);
        Assert.IsTrue(typeof(global::IScanner).IsInterface);
        Assert.IsTrue(typeof(global::IFaxSender).IsInterface);
        Assert.AreEqual(1, typeof(global::IPrinter).GetMethods().Length);
        Assert.AreEqual(1, typeof(global::IScanner).GetMethods().Length);
        Assert.AreEqual(1, typeof(global::IFaxSender).GetMethods().Length);
    }

    [TestMethod]
    public void implements_devices_with_real_capabilities_only()
    {
        Assert.IsTrue(typeof(global::BasicPrinter).GetInterfaces().Contains(typeof(global::IPrinter)));
        Assert.IsFalse(typeof(global::BasicPrinter).GetInterfaces().Contains(typeof(global::IScanner)));
        Assert.IsFalse(typeof(global::BasicPrinter).GetInterfaces().Contains(typeof(global::IFaxSender)));
        Assert.IsTrue(typeof(global::MultifunctionPrinter).GetInterfaces().Contains(typeof(global::IPrinter)));
        Assert.IsTrue(typeof(global::MultifunctionPrinter).GetInterfaces().Contains(typeof(global::IScanner)));
        Assert.IsTrue(typeof(global::MultifunctionPrinter).GetInterfaces().Contains(typeof(global::IFaxSender)));
    }

    [TestMethod]
    public void consumers_depend_only_on_needed_contract()
    {
        Assert.AreEqual(typeof(global::IPrinter), typeof(global::PrintService).GetConstructors().Single().GetParameters()[0].ParameterType);
        Assert.AreEqual(typeof(global::IScanner), typeof(global::ScanService).GetConstructors().Single().GetParameters()[0].ParameterType);
    }

    [TestMethod]
    public void avoids_unsupported_methods_on_general_contracts()
    {
        var printer = new global::BasicPrinter();
        var service = new global::PrintService(printer);

        Assert.AreEqual("printed: hello", service.Print("hello"));
    }
}

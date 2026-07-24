using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void removes_spaces_and_normalizes_case()
    {
        Assert.IsTrue(global::IbanValidator.IsValid("gb82 west 1234 5698 7654 32"));
    }

    [TestMethod]
    public void validates_characters_and_length()
    {
        Assert.IsFalse(global::IbanValidator.IsValid("GB82 WEST 1234 5698 7654 3!"));
        Assert.IsFalse(global::IbanValidator.IsValid("GB82"));
    }

    [TestMethod]
    public void implements_mod97_without_overflow()
    {
        Assert.IsTrue(global::IbanValidator.IsValid("DE89 3704 0044 0532 0130 00"));
        Assert.IsFalse(global::IbanValidator.IsValid("DE88 3704 0044 0532 0130 00"));
    }

    [TestMethod]
    public void formats_in_groups_of_four()
    {
        Assert.AreEqual("GB82 WEST 1234 5698 7654 32", global::IbanValidator.Format("gb82west12345698765432"));
    }

    [TestMethod]
    public void rejects_null_or_empty_input()
    {
        Assert.IsFalse(global::IbanValidator.IsValid(null));
        Assert.IsFalse(global::IbanValidator.IsValid("   "));
        Assert.ThrowsException<ArgumentException>(() => global::IbanValidator.Format(""));
    }
}

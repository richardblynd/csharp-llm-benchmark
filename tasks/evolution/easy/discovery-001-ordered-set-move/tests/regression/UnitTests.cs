using Collections;
using Microsoft.VisualStudio.TestTools.UnitTesting;
[TestClass] public class RegressionTests
{
    [TestMethod] public void old_add_retains_insertion_order_and_uniqueness()
    {var s=new OrderedSet<int>();Assert.IsTrue(s.Add(2));s.Add(1);Assert.IsFalse(s.Add(2));CollectionAssert.AreEqual(new[]{2,1},s.Items.ToArray());Assert.AreEqual(2,s.Count);}
    [TestMethod] public void old_remove_reports_presence_and_permits_readding()
    {var s=new OrderedSet<int>();s.Add(1);s.Add(2);Assert.IsTrue(s.Remove(1));Assert.IsFalse(s.Remove(1));s.Add(1);CollectionAssert.AreEqual(new[]{2,1},s.Items.ToArray());}
    [TestMethod] public void old_equality_is_used_without_replacing_values()
    {var s=new OrderedSet<string>(StringComparer.OrdinalIgnoreCase);s.Add("Hello");Assert.IsFalse(s.Add("HELLO"));Assert.IsTrue(s.Contains("hello"));Assert.AreEqual("Hello",s.Items[0]);Assert.IsTrue(s.Remove("hello"));}
    [TestMethod] public void old_null_and_default_values_are_supported()
    {var s=new OrderedSet<string?>();Assert.IsTrue(s.Add(null));Assert.IsTrue(s.Contains(null));Assert.IsFalse(s.Add(null));Assert.IsTrue(s.Remove(null));var n=new OrderedSet<int>();Assert.IsTrue(n.Add(0));Assert.IsTrue(n.Contains(0));}
    [TestMethod] public void old_snapshots_and_instances_are_independent()
    {var s=new OrderedSet<int>();s.Add(1);var snapshot=s.Items;((int[])snapshot)[0]=8;Assert.AreEqual(1,s.Items[0]);s.Add(2);Assert.AreEqual(1,snapshot.Count);Assert.AreEqual(0,new OrderedSet<int>().Count);}
}

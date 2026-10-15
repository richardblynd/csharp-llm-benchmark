using Collections;
using Microsoft.VisualStudio.TestTools.UnitTesting;
[TestClass] public class FeatureTests
{
    private static OrderedSet<int> Set() { var s = new OrderedSet<int>(); foreach (var n in new[] {1,2,3,4}) s.Add(n); return s; }
    [TestMethod] public void moves_in_both_directions_preserve_other_order()
    {
        var s = Set(); Assert.IsTrue(s.MoveBefore(4,2)); CollectionAssert.AreEqual(new[]{1,4,2,3},s.Items.ToArray());
        Assert.IsTrue(s.MoveAfter(1,3)); CollectionAssert.AreEqual(new[]{4,2,3,1},s.Items.ToArray()); Assert.AreEqual(4,s.Count);
    }
    [TestMethod] public void absent_values_leave_the_collection_unchanged()
    {
        var s = Set(); Assert.IsFalse(s.MoveBefore(9,2)); Assert.IsFalse(s.MoveAfter(2,9));
        Assert.IsFalse(s.MoveBefore(9,9)); CollectionAssert.AreEqual(new[]{1,2,3,4},s.Items.ToArray());
    }
    [TestMethod] public void self_and_adjacent_moves_succeed()
    {
        var s = Set(); Assert.IsTrue(s.MoveAfter(1,1)); Assert.IsTrue(s.MoveBefore(1,2));
        Assert.IsTrue(s.MoveAfter(4,3)); CollectionAssert.AreEqual(new[]{1,2,3,4},s.Items.ToArray());
    }
    [TestMethod] public void configured_equality_keeps_original_values()
    {
        var s = new OrderedSet<string>(StringComparer.OrdinalIgnoreCase); s.Add("Alpha");s.Add("Beta");s.Add("Gamma");
        Assert.IsTrue(s.MoveBefore("GAMMA","ALPHA")); CollectionAssert.AreEqual(new[]{"Gamma","Alpha","Beta"},s.Items.ToArray());
        Assert.IsTrue(s.MoveAfter("alpha","BETA")); CollectionAssert.AreEqual(new[]{"Gamma","Beta","Alpha"},s.Items.ToArray());
    }
    [TestMethod] public void null_default_and_snapshots_interoperate_with_moves()
    {
        var s = new OrderedSet<string?>();s.Add(null);s.Add("x");s.Add("y");var before=s.Items;
        Assert.IsTrue(s.MoveAfter(null,"y")); Assert.IsNull(s.Items[2]); Assert.IsNull(before[0]);
        Assert.IsTrue(s.Remove(null)); Assert.IsTrue(s.Add(null)); Assert.AreEqual(3,s.Count);
    }
}

using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void sorts_by_last_name()
    {
        var result = global::Solution.Execute(new[]
        {
            Person("Bob", "Zulu", 20),
            Person("Ann", "Alpha", 20)
        });
        Assert.AreEqual("Alpha", result[0].LastName);
    }

    [TestMethod]
    public void sorts_by_first_name_when_last_name_matches()
    {
        var result = global::Solution.Execute(new[]
        {
            Person("Zoey", "Stone", 20),
            Person("Adam", "Stone", 20)
        });
        Assert.AreEqual("Adam", result[0].FirstName);
    }

    [TestMethod]
    public void sorts_by_age_descending_when_names_match()
    {
        var result = global::Solution.Execute(new[]
        {
            Person("Sam", "Lee", 20),
            Person("Sam", "Lee", 45)
        });
        Assert.AreEqual(45, result[0].Age);
    }

    [TestMethod]
    public void does_not_mutate_input_order()
    {
        var people = new List<global::Person>
        {
            Person("B", "B", 1),
            Person("A", "A", 1)
        };
        _ = global::Solution.Execute(people);
        Assert.AreEqual("B", people[0].FirstName);
    }

    private static global::Person Person(string first, string last, int age)
    {
        return new global::Person { FirstName = first, LastName = last, Age = age };
    }
}

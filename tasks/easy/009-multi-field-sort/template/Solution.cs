public class Person
{
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public int Age { get; set; }
}

public class Solution
{
    public static List<Person> Execute(IEnumerable<Person> people) => people.ToList();
}

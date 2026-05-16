using System;
using System.Collections.Generic;
using System.Linq;

public sealed class PersistentTrieMap<T>
{
    private sealed class Node
    {
        public Node(bool hasValue, T? value, SortedDictionary<char, Node>? children = null)
        {
            HasValue = hasValue;
            Value = value;
            Children = children ?? new SortedDictionary<char, Node>();
        }

        public bool HasValue { get; }
        public T? Value { get; }
        public SortedDictionary<char, Node> Children { get; }
    }

    private static readonly PersistentTrieMap<T> EmptyInstance = new(new Node(false, default), 0);
    private readonly Node root;

    private PersistentTrieMap(Node root, int count)
    {
        this.root = root;
        Count = count;
    }

    public static PersistentTrieMap<T> Empty => EmptyInstance;
    public int Count { get; }

    public PersistentTrieMap<T> Set(string key, T value)
    {
        ArgumentNullException.ThrowIfNull(key);
        var existed = TryGetValue(key, out _);
        var nextRoot = Set(root, key, 0, value);
        return new PersistentTrieMap<T>(nextRoot, existed ? Count : Count + 1);
    }

    public PersistentTrieMap<T> Remove(string key)
    {
        ArgumentNullException.ThrowIfNull(key);
        if (!TryGetValue(key, out _))
        {
            return this;
        }

        return new PersistentTrieMap<T>(Remove(root, key, 0), Count - 1);
    }

    public bool TryGetValue(string key, out T value)
    {
        ArgumentNullException.ThrowIfNull(key);
        var current = root;
        foreach (var character in key)
        {
            if (!current.Children.TryGetValue(character, out var child))
            {
                value = default!;
                return false;
            }

            current = child;
        }

        if (!current.HasValue)
        {
            value = default!;
            return false;
        }

        value = current.Value!;
        return true;
    }

    public IReadOnlyList<KeyValuePair<string, T>> ScanPrefix(string prefix)
    {
        ArgumentNullException.ThrowIfNull(prefix);
        var current = root;
        foreach (var character in prefix)
        {
            if (!current.Children.TryGetValue(character, out var child))
            {
                return Array.Empty<KeyValuePair<string, T>>();
            }

            current = child;
        }

        var result = new List<KeyValuePair<string, T>>();
        Collect(current, prefix, result);
        return result;
    }

    private static Node Set(Node node, string key, int index, T value)
    {
        if (index == key.Length)
        {
            return new Node(true, value, CloneChildren(node));
        }

        var children = CloneChildren(node);
        children.TryGetValue(key[index], out var existing);
        children[key[index]] = Set(existing ?? new Node(false, default), key, index + 1, value);
        return new Node(node.HasValue, node.Value, children);
    }

    private static Node Remove(Node node, string key, int index)
    {
        if (index == key.Length)
        {
            return new Node(false, default, CloneChildren(node));
        }

        var children = CloneChildren(node);
        var child = children[key[index]];
        var nextChild = Remove(child, key, index + 1);
        if (!nextChild.HasValue && nextChild.Children.Count == 0)
        {
            children.Remove(key[index]);
        }
        else
        {
            children[key[index]] = nextChild;
        }

        return new Node(node.HasValue, node.Value, children);
    }

    private static void Collect(Node node, string key, List<KeyValuePair<string, T>> result)
    {
        if (node.HasValue)
        {
            result.Add(new KeyValuePair<string, T>(key, node.Value!));
        }

        foreach (var (character, child) in node.Children)
        {
            Collect(child, key + character, result);
        }
    }

    private static SortedDictionary<char, Node> CloneChildren(Node node)
    {
        return new SortedDictionary<char, Node>(node.Children);
    }
}

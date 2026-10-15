Add a public JsonFormatter implementing the existing IReportFormatter. Its Format is "json".
Render returns a JSON array, preserving row order and duplicates. Each element has exactly
the properties "name" (the original name) and "value" (a JSON number, not a string).
Handle quotes, control characters and Unicode correctly; numbers must not depend on culture.
Register it in the default ReportService so Export("json", rows) works, case-insensitively.
The custom-formatter constructor must still use only the supplied formatters, with unchanged
duplicate/unknown-format validation. Preserve text/CSV output and all existing contracts.
Use the existing formatter interface and service, without additional dependencies.

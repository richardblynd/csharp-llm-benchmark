ReportService exports rows with registered IReportFormatter implementations. The default
constructor provides text and CSV. The params constructor snapshots the supplied formatter
array, matches format identifiers case-insensitively, rejects nulls and duplicate identifiers.
Export rejects null format/rows and unknown formats, snapshots the input sequence once and
passes it to the selected formatter. Text joins "Name: Value" lines with LF. CSV starts with
"name,value" plus LF, quotes every name and doubles embedded quotes. Numbers use invariant
culture. Empty text is empty; empty CSV is "name,value" followed by LF. Custom output is unchanged.

Build: dotnet build Reports.csproj --configuration Release

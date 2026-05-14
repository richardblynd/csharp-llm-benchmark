var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddSingleton<DocumentStore>();

var app = builder.Build();
app.MapControllers();
app.Run();

public partial class Program { }

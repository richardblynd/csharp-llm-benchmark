var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddSingleton<PaymentStore>();

var app = builder.Build();
app.MapControllers();
app.Run();

public partial class Program { }

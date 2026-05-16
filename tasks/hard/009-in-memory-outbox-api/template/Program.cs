var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddSingleton<OutboxStore>();
builder.Services.AddSingleton<IEventPublisher, RecordingEventPublisher>();
builder.Services.AddSingleton<OutboxWorker>();
builder.Services.AddHostedService(provider => provider.GetRequiredService<OutboxWorker>());

var app = builder.Build();
app.MapControllers();
app.Run();

public partial class Program { }

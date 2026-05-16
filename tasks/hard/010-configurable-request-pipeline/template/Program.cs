using Microsoft.Extensions.Options;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSingleton<IValidateOptions<RequestPipelineOptions>, RequestPipelineOptionsValidator>();
builder.Services.AddOptions<RequestPipelineOptions>()
    .Bind(builder.Configuration.GetSection("Pipeline"))
    .ValidateOnStart();
builder.Services.AddSingleton<IRoutePolicyEvaluator, HeaderRoutePolicyEvaluator>();
builder.Services.AddControllers(options => options.Filters.Add<RoutePolicyFilter>());

var app = builder.Build();
app.UseMiddleware<CorrelationIdMiddleware>();
app.UseMiddleware<DomainExceptionMiddleware>();
app.MapControllers();
app.Run();

public partial class Program { }

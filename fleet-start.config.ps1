# Per-repo fleet start config for scraper-mcp
# Edit ports/backend target here - start.ps1 is fleet-standard.
@{
    Name         = 'scraper-mcp'
    BackendPort  = 10998
    FrontendPort = 10999
    HealthPath   = '/health'
    WebRoot      = 'D:\Dev\repos\scraper-mcp\webapp'
    Backend = @{
        Kind          = 'uvicorn'
        UvicornTarget = 'scraper_mcp.app:app'
        SyncExtras    = @('dev')
        Env           = @{ WEB_PORT = '10998' }
    }
    Frontend = @{
        Kind           = 'vite-npm'
        PackageManager = 'npm'
        PortEnvVar     = 'VITE_PORT'
        ApiTargetEnv   = 'VITE_API_TARGET'
    }
}

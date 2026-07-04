# Troubleshooting

## Deployment fails with "build error"

If your deployment fails with a build error, check the build logs from the
Deployments tab. The most common causes are a missing dependency in your
manifest file or an incompatible runtime version. Pin your runtime version in
the project settings to avoid unexpected upgrades.

## Application returns 502 Bad Gateway

A 502 error usually means your application crashed or is not listening on the
expected port. Make sure your app binds to the port provided by the PORT
environment variable. Check the runtime logs for stack traces.

## Slow response times

If your application is slow, first check the metrics dashboard for CPU and memory
usage. If you are consistently near your resource limits, scale up your instance
size or enable autoscaling under Settings -> Scaling.

## Custom domain not working

After adding a custom domain, you must add a CNAME record at your DNS provider
pointing to your Acme Cloud endpoint. DNS changes can take up to 48 hours to
propagate. TLS certificates are provisioned automatically once the DNS record is
verified.

## Contacting support

If none of these steps resolve your issue, contact support through the in-app
chat widget or email support@acme.example. Growth and Scale plan customers
receive priority responses.

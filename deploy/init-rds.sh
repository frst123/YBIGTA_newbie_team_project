#!/usr/bin/env bash
set -euo pipefail

: "${RDS_ENDPOINT:?Set RDS_ENDPOINT to the CloudFormation RdsEndpoint output}"
: "${RDS_MASTER_PASSWORD:?Set the RDS master password for this one-time setup}"
: "${COLLECTOR_DB_PASSWORD:?Set a password for collector_user}"
: "${MCP_DB_PASSWORD:?Set a password for mcp_user}"
RDS_MASTER_USERNAME=${RDS_MASTER_USERNAME:-dbadmin}

mysql_run() {
  docker run --rm -i -e MYSQL_PWD="$RDS_MASTER_PASSWORD" mysql:8 \
    mysql -h "$RDS_ENDPOINT" -u "$RDS_MASTER_USERNAME" review_pipeline
}

sql_quote() {
  local value=$1
  value=${value//\\/\\\\}
  value=${value//\'/\'\'}
  printf "%s" "$value"
}

mysql_run < infra/rds/init.sql
collector_password=$(sql_quote "$COLLECTOR_DB_PASSWORD")
mcp_password=$(sql_quote "$MCP_DB_PASSWORD")
printf "CREATE USER IF NOT EXISTS 'collector_user'@'%%' IDENTIFIED BY '%s';\n" "$collector_password" | mysql_run
printf "CREATE USER IF NOT EXISTS 'mcp_user'@'%%' IDENTIFIED BY '%s';\n" "$mcp_password" | mysql_run
printf '%s\n' \
  "GRANT SELECT, INSERT, UPDATE ON review_pipeline.reviews TO 'collector_user'@'%';" \
  "GRANT SELECT ON review_pipeline.reviews TO 'mcp_user'@'%';" \
  'FLUSH PRIVILEGES;' | mysql_run

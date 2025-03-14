function queryParams(params) {
    return {
        limit: params.limit,
        offset: params.offset,
        sort: params.sort,
        order: params.order,
        search: params.search
    };
}

function responseHandler(res) {
    return {
        total: res.total,
        rows: res.rows
    };
}
import streamlit as st
import akshare as ak
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
import time
from functools import lru_cache

# 带重试机制的数据获取函数
@lru_cache(maxsize=32)
def get_data_with_retry(symbol, start_date, end_date, max_retries=3):
    for attempt in range(max_retries):
        try:
            df = ak.stock_board_industry_hist_em(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                adjust=""
            )
            return df
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # 指数退避

# 优化后的数据获取函数
@st.cache_data(ttl=3600)
def get_board_data():
    board_df = ak.stock_board_industry_name_em()
    data_list = []

    for index, row in board_df.iterrows():
        try:
            df = get_data_with_retry(
                row["板块名称"],
                (datetime.now() - timedelta(days=7)).strftime("%Y%m%d"),
                datetime.now().strftime("%Y%m%d")
            )
            latest = df.iloc[-1].to_dict()
            latest["板块名称"] = row["板块名称"]
            data_list.append(latest)
        except Exception as e:
            st.warning(f"获取 {row['板块名称']} 数据失败: {str(e)}")
            continue

    return pd.DataFrame(data_list)

# 优化后的数据处理函数
def process_data(df):
    numeric_cols = ['开盘', '收盘', '最高', '最低', '成交量', '成交额', '振幅', '涨跌幅', '换手率']
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')

    # 新增指标
    df['量价强度'] = df['涨跌幅'] * df['换手率']
    df['成交额（亿）'] = df['成交额'] / 1e8
    df['成交量（万手）'] = df['成交量'] / 10000
    df['涨跌幅'] = df['涨跌幅'] * 100

    # 数据清洗
    df = df.dropna(subset=['涨跌幅'])
    df = df[df['成交量'] > 0]  # 过滤无效数据

    return df

# 主程序
def main():
    st.set_page_config(
        page_title="板块资金热力图",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("📈 实时板块资金流向热力图")
    st.markdown("""
    **数据说明：**
    - 颜色映射：绿色表示下跌，红色表示上涨
    - 数据更新：{} 
    """.format(datetime.now().strftime("%Y-%m-%d %H:%M")))

    # 侧边栏控件
    with st.sidebar:
        st.header("参数设置")
        color_metric = st.selectbox(
            "颜色指标",
            options=['涨跌幅', '换手率', '量价强度'],
            index=0
        )
        size_metric = st.selectbox(
            "板块大小指标",
            options=['成交额（亿）', '成交量（万手）', '换手率'],
            index=0
        )
        date_range = st.slider(
            "回溯天数",
            min_value=1,
            max_value=30,
            value=7
        )
        color_scale = st.selectbox(
            "配色方案",
            options=['RdYlGn_r', 'BrBG_r', 'PiYG_r', 'RdBu_r'],  # 全部使用反转色阶
            index=0
        )

    # 数据加载
    with st.spinner('正在获取最新行情数据...'):
        raw_df = get_board_data()
        processed_df = process_data(raw_df)

    # 数据过滤
    filtered_df = processed_df[
        processed_df['日期'] >= (datetime.now() - timedelta(days=date_range)).strftime("%Y-%m-%d")
    ]

    # 检查过滤后是否有数据
    if filtered_df.empty:
        st.warning("过滤后无有效数据，请调整参数。")
        return

    # 检查 color_metric 数据是否唯一
    if filtered_df[color_metric].nunique() == 1:
        # 如果所有值都相同，手动设置 range_color 范围
        range_color = [filtered_df[color_metric].min() - 1, filtered_df[color_metric].max() + 1]
    else:
        range_color = [filtered_df[color_metric].min(), filtered_df[color_metric].max()]

    try:
        # 创建可视化
        fig = px.treemap(
            filtered_df,
            path=['板块名称'],
            values=size_metric,
            color=color_metric,
            color_continuous_scale=color_scale,
            range_color=range_color,
            hover_data={
                '涨跌幅': ':.2f%',
                '换手率': ':.2f%',
                '成交额（亿）': ':.2f',
                '量价强度': ':.2f'
            },
            height=800
        )

        # 样式调整
        try:
            fig.update_layout(
                margin=dict(t=40, l=20, r=20, b=20),
                coloraxis_colorbar=dict(
                    title=dict(
                        text=color_metric + (" (%)" if color_metric == "涨跌幅" else ""),
                        side="right"  # 修改为正确的属性设置方式
                    ),
                    tickformat="+.1%" if color_metric == "涨跌幅" else ".1f",
                    thickness=15
                ),
                plot_bgcolor='rgba(240,240,240,0.8)'
            )
        except Exception as e:
            st.error(f"更新图表布局时出错: {e}")
            return

    except Exception as e:
        st.error(f"创建图表时出现错误: {e}")
        return

    st.plotly_chart(fig, use_container_width=True)

    # 数据表格
    with st.expander("查看原始数据"):
        st.dataframe(
            filtered_df.sort_values(by='涨跌幅', ascending=False),
            column_config={
                "日期": "日期",
                "板块名称": st.column_config.TextColumn(width="large"),
                "涨跌幅": st.column_config.NumberColumn(format="▁%.2f%%",
                                                        help="颜色映射："),
                "换手率": st.column_config.NumberColumn(format="%.2f%%"),
                "成交额（亿）": st.column_config.NumberColumn(format="%.1f 亿")
            },
            height=300,
            hide_index=True
        )


if __name__ == "__main__":
    main()

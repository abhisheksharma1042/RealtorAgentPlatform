/* eslint-disable @typescript-eslint/no-explicit-any */
// TODO(types): replace `any` echarts callback params with proper echarts-for-react types.
// This chart pre-dates the data-ingestion feature; left untyped to avoid scope creep here.
import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'

interface BarChartProps {
  data: Array<{ name: string; value: number }>
  title?: string
  xAxisLabel?: string
  yAxisLabel?: string
  horizontal?: boolean
}

export default function BarChart({
  data,
  title = 'Comparison',
  xAxisLabel,
  yAxisLabel,
  horizontal = false,
}: BarChartProps) {
  const option = useMemo(() => {
    const names = data.map((d) => d.name)
    const values = data.map((d) => d.value)

    const baseConfig = {
      title: {
        text: title,
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 'normal',
        },
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow',
        },
        formatter: (params: any) => {
          const param = params[0]
          return `${param.name}<br/><strong>${param.value.toLocaleString()}</strong>`
        },
      },
      grid: {
        left: horizontal ? '15%' : '10%',
        right: '10%',
        bottom: '15%',
        top: '15%',
      },
    }

    if (horizontal) {
      return {
        ...baseConfig,
        xAxis: {
          type: 'value',
          name: xAxisLabel,
          axisLabel: {
            formatter: (value: number) => value.toLocaleString(),
          },
        },
        yAxis: {
          type: 'category',
          data: names,
          name: yAxisLabel,
        },
        series: [
          {
            type: 'bar',
            data: values,
            itemStyle: {
              color: '#3b82f6',
            },
            emphasis: {
              itemStyle: {
                color: '#2563eb',
              },
            },
          },
        ],
      }
    }

    return {
      ...baseConfig,
      xAxis: {
        type: 'category',
        data: names,
        name: xAxisLabel,
        axisLabel: {
          rotate: 45,
          fontSize: 11,
        },
      },
      yAxis: {
        type: 'value',
        name: yAxisLabel,
        axisLabel: {
          formatter: (value: number) => value.toLocaleString(),
        },
      },
      series: [
        {
          type: 'bar',
          data: values,
          itemStyle: {
            color: '#3b82f6',
          },
          emphasis: {
            itemStyle: {
              color: '#2563eb',
            },
          },
        },
      ],
    }
  }, [data, title, xAxisLabel, yAxisLabel, horizontal])

  return (
    <div className="w-full">
      <ReactECharts option={option} style={{ height: '400px' }} />
    </div>
  )
}

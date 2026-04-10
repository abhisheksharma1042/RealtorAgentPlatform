import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'

interface Property {
  address?: string
  sqft?: number
  price?: number
  sold_price?: number
  beds?: number
  baths?: number
}

interface ScatterChartProps {
  data: Property[]
  title?: string
  xAxis?: string
  yAxis?: string
}

export default function ScatterChart({
  data,
  title = 'Property Comparison',
  xAxis = 'sqft',
  yAxis = 'price',
}: ScatterChartProps) {
  const option = useMemo(() => {
    // Extract data points
    const scatterData = data.map((prop) => {
      const x = prop[xAxis as keyof Property] || prop.sqft
      const y = prop[yAxis as keyof Property] || prop.sold_price || prop.price
      return {
        value: [x, y],
        name: prop.address,
        itemStyle: {
          color: '#3b82f6', // blue
        },
      }
    })

    return {
      title: {
        text: title,
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 'normal',
        },
      },
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          const prop = data[params.dataIndex]
          return `
            <div style="font-size: 12px;">
              <strong>${prop.address || 'Property'}</strong><br/>
              ${prop.beds || '?'} bed, ${prop.baths || '?'} bath<br/>
              ${prop.sqft?.toLocaleString() || '?'} sqft<br/>
              <strong>$${(prop.sold_price || prop.price)?.toLocaleString() || '?'}</strong>
            </div>
          `
        },
      },
      grid: {
        left: '10%',
        right: '10%',
        bottom: '15%',
        top: '15%',
      },
      xAxis: {
        name: xAxis === 'sqft' ? 'Square Feet' : xAxis,
        nameLocation: 'center',
        nameGap: 30,
        type: 'value',
        axisLabel: {
          formatter: (value: number) => value.toLocaleString(),
        },
      },
      yAxis: {
        name: yAxis === 'price' || yAxis === 'sold_price' ? 'Price ($)' : yAxis,
        nameLocation: 'center',
        nameGap: 50,
        type: 'value',
        axisLabel: {
          formatter: (value: number) => `$${(value / 1000).toFixed(0)}K`,
        },
      },
      series: [
        {
          type: 'scatter',
          data: scatterData,
          symbolSize: 10,
          emphasis: {
            scale: 1.5,
          },
        },
      ],
    }
  }, [data, title, xAxis, yAxis])

  return (
    <div className="w-full">
      <ReactECharts option={option} style={{ height: '400px' }} />
    </div>
  )
}

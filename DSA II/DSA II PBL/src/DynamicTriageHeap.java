import java.util.ArrayList;

public class DynamicTriageHeap {
    private ArrayList<PatientNode> heap;

    public DynamicTriageHeap() {
        this.heap = new ArrayList<>();
    }

    public void insert(PatientNode p) {
        heap.add(p);
        bubbleUp(heap.size() - 1);
    }

    public PatientNode extractMax() {
        if (heap.isEmpty()) return null;
        if (heap.size() == 1) return heap.remove(0);

        PatientNode max = heap.get(0);
        PatientNode last = heap.remove(heap.size() - 1);
        heap.set(0, last);
        sinkDown(0);
        return max;
    }

    public PatientNode peek() {
        return heap.isEmpty() ? null : heap.get(0);
    }

    public int size() {
        return heap.size();
    }

    public boolean isEmpty() {
        return heap.isEmpty();
    }

    private void bubbleUp(int index) {
        while (index > 0) {
            int parentIndex = (index - 1) / 2;
            if (heap.get(index).compareTo(heap.get(parentIndex)) < 0) {
                swap(index, parentIndex);
                index = parentIndex;
            } else {
                break;
            }
        }
    }

    private void sinkDown(int index) {
        int size = heap.size();
        while (index < size) {
            int left = 2 * index + 1;
            int right = 2 * index + 2;
            int highestPriority = index;

            if (left < size && heap.get(left).compareTo(heap.get(highestPriority)) < 0) {
                highestPriority = left;
            }
            if (right < size && heap.get(right).compareTo(heap.get(highestPriority)) < 0) {
                highestPriority = right;
            }

            if (highestPriority != index) {
                swap(index, highestPriority);
                index = highestPriority;
            } else {
                break;
            }
        }
    }

    private void swap(int i, int j) {
        PatientNode temp = heap.get(i);
        heap.set(i, heap.get(j));
        heap.set(j, temp);
    }

    public void printQueue() {
        System.out.println("---------------- Current Triage Max-Heap Queue ----------------");
        for (PatientNode p : heap) {
            System.out.println("  " + p);
        }
        System.out.println("----------------------------------------------------------------");
    }
}
